import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef } from 'react';
import { useToast } from '@/components/ui/use-toast';
import { apiClient } from '@/lib/api/client';
import type { GenerationResponse, HistoryListResponse } from '@/lib/api/types';
import { useGenerationSettings } from '@/lib/hooks/useSettings';
import { useGenerationStore } from '@/stores/generationStore';
import { usePlayerStore } from '@/stores/playerStore';

interface GenerationStatusEvent {
  id: string;
  status: 'loading_model' | 'generating' | 'completed' | 'failed' | 'not_found';
  duration?: number;
  error?: string;
  source?: string;
}

function normalizeStatus(
  status: GenerationStatusEvent['status'],
): GenerationResponse['status'] {
  return status === 'not_found' ? 'failed' : status;
}

// Agent-initiated generations are played by the floating pill, not the
// main-window AudioPlayer. Skip autoplay here to avoid double-playback.
const AGENT_SOURCES = new Set(['mcp', 'rest']);

/**
 * Subscribes to SSE for all pending generations. When a generation completes,
 * invalidates the history query, removes it from pending, and auto-plays
 * if the player is idle.
 */
export function useGenerationProgress() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const pendingIds = useGenerationStore((s) => s.pendingGenerationIds);
  const removePendingGeneration = useGenerationStore((s) => s.removePendingGeneration);
  const removePendingStoryAdd = useGenerationStore((s) => s.removePendingStoryAdd);
  const isPlaying = usePlayerStore((s) => s.isPlaying);
  const setAudioWithAutoPlay = usePlayerStore((s) => s.setAudioWithAutoPlay);
  const { settings: genSettings } = useGenerationSettings();
  const autoplayOnGenerate = genSettings?.autoplay_on_generate ?? true;

  const patchGenerationStatusInCache = useCallback(
    (event: GenerationStatusEvent) => {
      // Keep history list rows in sync immediately while background refetch catches up.
      queryClient.setQueriesData<HistoryListResponse>(
        { queryKey: ['history'] },
        (prev) => {
          if (!prev) return prev;

          let touched = false;
          const items = prev.items.map((item) => {
            if (item.id !== event.id) return item;
            touched = true;
            const nextStatus = normalizeStatus(event.status);
            return {
              ...item,
              status: nextStatus,
              duration: event.duration ?? item.duration,
              error:
                nextStatus === 'failed'
                  ? event.error || item.error
                  : nextStatus === 'completed'
                    ? undefined
                    : item.error,
            };
          });

          return touched ? { ...prev, items } : prev;
        },
      );

      // Also patch generation detail query (['history', id]) when present.
      queryClient.setQueryData<GenerationResponse>(['history', event.id], (prev) => {
        if (!prev) return prev;
        const nextStatus = normalizeStatus(event.status);
        return {
          ...prev,
          status: nextStatus,
          duration: event.duration ?? prev.duration,
          error:
            nextStatus === 'failed'
              ? event.error || prev.error
              : nextStatus === 'completed'
                ? undefined
                : prev.error,
        };
      });
    },
    [queryClient],
  );

  // Keep refs to avoid stale closures in EventSource handlers
  const isPlayingRef = useRef(isPlaying);
  const autoplayRef = useRef(autoplayOnGenerate);
  isPlayingRef.current = isPlaying;
  autoplayRef.current = autoplayOnGenerate;

  // Track active EventSource instances
  const eventSourcesRef = useRef<Map<string, EventSource>>(new Map());

  // Unmount-only cleanup — close all SSE connections when the hook is torn down
  useEffect(() => {
    const sources = eventSourcesRef.current;
    return () => {
      for (const source of sources.values()) {
        source.close();
      }
      sources.clear();
    };
  }, []);

  useEffect(() => {
    const currentSources = eventSourcesRef.current;

    // Close SSE connections for IDs no longer pending
    for (const [id, source] of currentSources.entries()) {
      if (!pendingIds.has(id)) {
        source.close();
        currentSources.delete(id);
      }
    }

    // Open SSE connections for new pending IDs
    for (const id of pendingIds) {
      if (currentSources.has(id)) continue;

      const url = apiClient.getGenerationStatusUrl(id);
      const source = new EventSource(url);

      source.onmessage = (event) => {
        try {
          const data: GenerationStatusEvent = JSON.parse(event.data);
          patchGenerationStatusInCache(data);

          if (data.status === 'completed') {
            source.close();
            currentSources.delete(id);
            removePendingGeneration(id);

            // Refetch history to pick up the completed generation
            queryClient.refetchQueries({ queryKey: ['history'] });

            // If this generation was queued for a story, add it now
            const storyId = removePendingStoryAdd(id);
            if (storyId) {
              apiClient
                .addStoryItem(storyId, { generation_id: id })
                .then(() => {
                  queryClient.invalidateQueries({ queryKey: ['stories'] });
                  queryClient.invalidateQueries({ queryKey: ['stories', storyId] });
                  toast({
                    title: 'Added to story',
                    description: data.duration
                      ? `Audio generated (${data.duration.toFixed(2)}s) and added to story`
                      : 'Audio generated and added to story',
                  });
                })
                .catch(() => {
                  toast({
                    title: 'Generation complete',
                    description: 'Audio generated but failed to add to story',
                    variant: 'destructive',
                  });
                });
            } else {
              // toast({
              //   title: 'Generation complete!',
              //   description: data.duration
              //     ? `Audio generated (${data.duration.toFixed(2)}s)`
              //     : 'Audio generated',
              // });
            }

            // Auto-play if enabled and nothing is currently playing.
            // Skip agent-initiated sources — the floating pill window
            // plays those itself.
            const isAgentSpeak = data.source ? AGENT_SOURCES.has(data.source) : false;
            if (autoplayRef.current && !isPlayingRef.current && !isAgentSpeak) {
              const genAudioUrl = apiClient.getAudioUrl(id);
              setAudioWithAutoPlay(genAudioUrl, id, '', '');
            }
          } else if (data.status === 'failed' || data.status === 'not_found') {
            source.close();
            currentSources.delete(id);
            removePendingGeneration(id);
            removePendingStoryAdd(id);

            queryClient.refetchQueries({ queryKey: ['history'] });

            toast({
              title: data.status === 'not_found' ? 'Generation not found' : 'Generation failed',
              description: data.error || 'An error occurred during generation',
              variant: 'destructive',
            });
          }
        } catch {
          // Ignore parse errors from heartbeats etc
        }
      };

      source.onerror = () => {
        // SSE connection dropped — clean up and refresh history so any
        // completed/failed generation still appears in the list
        source.close();
        currentSources.delete(id);
        removePendingGeneration(id);
        queryClient.refetchQueries({ queryKey: ['history'] });
      };

      currentSources.set(id, source);
    }
  }, [
    pendingIds,
    removePendingGeneration,
    removePendingStoryAdd,
    patchGenerationStatusInCache,
    queryClient,
    toast,
    setAudioWithAutoPlay,
  ]);
}
