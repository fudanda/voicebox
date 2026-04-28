import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef } from 'react';
import { useToast } from '@/components/ui/use-toast';
import { apiClient } from '@/lib/api/client';
import type { GenerationResponse, HistoryListResponse } from '@/lib/api/types';
import { useGenerationStore } from '@/stores/generationStore';
import { usePlayerStore } from '@/stores/playerStore';
import { useServerStore } from '@/stores/serverStore';

interface GenerationStatusEvent {
  id: string;
  status: 'loading_model' | 'generating' | 'completed' | 'failed' | 'not_found';
  duration?: number;
  error?: string;
}

function patchGenerationEntry<T extends { id: string; status: string; duration?: number; error?: string }>(
  entry: T,
  data: GenerationStatusEvent,
): T {
  if (entry.id !== data.id) return entry;
  return {
    ...entry,
    status: data.status === 'not_found' ? entry.status : data.status,
    duration: data.duration ?? entry.duration,
    error: data.error ?? (data.status === 'completed' ? undefined : entry.error),
  };
}

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
  const autoplayOnGenerate = useServerStore((s) => s.autoplayOnGenerate);

  const patchGenerationStatusInCache = useCallback((data: GenerationStatusEvent) => {
    queryClient.setQueriesData({ queryKey: ['history'] }, (oldData: unknown) => {
      if (!oldData || typeof oldData !== 'object') {
        return oldData;
      }

      const maybeList = oldData as Partial<HistoryListResponse>;
      if (Array.isArray(maybeList.items)) {
        let changed = false;
        const nextItems = maybeList.items.map((item) => {
          if (item.id !== data.id) return item;
          changed = true;
          return patchGenerationEntry(item, data);
        });
        return changed ? { ...maybeList, items: nextItems } : oldData;
      }

      const maybeDetail = oldData as Partial<GenerationResponse>;
      if (typeof maybeDetail.id === 'string' && typeof maybeDetail.status === 'string') {
        if (maybeDetail.id !== data.id) return oldData;
        return patchGenerationEntry(maybeDetail as GenerationResponse, data);
      }

      return oldData;
    });
  }, [queryClient]);

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

            // Auto-play if enabled and nothing is currently playing
            if (autoplayRef.current && !isPlayingRef.current) {
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
