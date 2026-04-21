import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import { apiClient } from '@/lib/api/client';
import type {
  TranscriptionSubtitlesResponse,
  WhisperModelSize,
} from '@/lib/api/types';
import {
  LANGUAGE_OPTIONS,
  type LanguageCode,
} from '@/lib/constants/languages';
import { BOTTOM_SAFE_AREA_PADDING } from '@/lib/constants/ui';
import { useModelDownloadToast } from '@/lib/hooks/useModelDownloadToast';
import { useProfileSamples, useProfiles } from '@/lib/hooks/useProfiles';
import { usePlatform } from '@/platform/PlatformContext';
import { usePlayerStore } from '@/stores/playerStore';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

type SourceMode = 'upload' | 'sample';
type LanguageSelection = LanguageCode | 'auto';

const WHISPER_MODELS: WhisperModelSize[] = ['base', 'small', 'medium', 'large', 'turbo'];

function pad2(value: number): string {
  return value.toString().padStart(2, '0');
}

function pad3(value: number): string {
  return value.toString().padStart(3, '0');
}

function formatSubtitleTimestamp(seconds: number, separator: ',' | '.'): string {
  const safeSeconds = Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
  const totalMs = Math.round(safeSeconds * 1000);

  const hours = Math.floor(totalMs / 3_600_000);
  const minutes = Math.floor((totalMs % 3_600_000) / 60_000);
  const secs = Math.floor((totalMs % 60_000) / 1000);
  const millis = totalMs % 1000;

  return `${pad2(hours)}:${pad2(minutes)}:${pad2(secs)}${separator}${pad3(millis)}`;
}

function buildSrt(response: TranscriptionSubtitlesResponse): string {
  return response.segments
    .map((segment, idx) => {
      const start = formatSubtitleTimestamp(segment.start, ',');
      const end = formatSubtitleTimestamp(segment.end, ',');
      return `${idx + 1}\n${start} --> ${end}\n${segment.text.trim()}`;
    })
    .join('\n\n');
}

function buildVtt(response: TranscriptionSubtitlesResponse): string {
  const cues = response.segments
    .map((segment) => {
      const start = formatSubtitleTimestamp(segment.start, '.');
      const end = formatSubtitleTimestamp(segment.end, '.');
      return `${start} --> ${end}\n${segment.text.trim()}`;
    })
    .join('\n\n');
  return `WEBVTT\n\n${cues}`;
}

function buildTxt(response: TranscriptionSubtitlesResponse): string {
  return response.text;
}

function isPendingDownloadError(error: unknown): error is Error & { downloading: boolean; modelName?: string } {
  return (
    error instanceof Error &&
    typeof (error as { downloading?: unknown }).downloading === 'boolean' &&
    (error as { downloading?: boolean }).downloading === true
  );
}

export function TranscriptionTab() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const platform = usePlatform();
  const isPlayerVisible = !!usePlayerStore((state) => state.audioUrl);

  const [sourceMode, setSourceMode] = useState<SourceMode>('upload');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedProfileId, setSelectedProfileId] = useState<string>('');
  const [selectedSampleId, setSelectedSampleId] = useState<string>('');
  const [language, setLanguage] = useState<LanguageSelection>('auto');
  const [model, setModel] = useState<WhisperModelSize>('base');
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [result, setResult] = useState<TranscriptionSubtitlesResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [downloadingModelName, setDownloadingModelName] = useState<string | null>(null);

  const { data: profiles = [] } = useProfiles();
  const { data: samples = [] } = useProfileSamples(selectedProfileId);

  useEffect(() => {
    if (!selectedProfileId && profiles.length > 0) {
      setSelectedProfileId(profiles[0].id);
    }
  }, [profiles, selectedProfileId]);

  useEffect(() => {
    if (!samples.length) {
      setSelectedSampleId('');
      return;
    }
    if (!selectedSampleId || !samples.some((sample) => sample.id === selectedSampleId)) {
      setSelectedSampleId(samples[0].id);
    }
  }, [samples, selectedSampleId]);

  useModelDownloadToast({
    modelName: downloadingModelName ?? '',
    displayName: downloadingModelName ?? '',
    enabled: !!downloadingModelName,
    onComplete: () => {
      setDownloadingModelName(null);
      toast({
        title: t('transcription.toast.modelReady'),
        description: t('transcription.toast.modelReadyDescription'),
      });
    },
    onError: (error) => {
      setDownloadingModelName(null);
      toast({
        title: t('transcription.toast.failed'),
        description: error,
        variant: 'destructive',
      });
    },
  });

  const runTranscription = async () => {
    if (sourceMode === 'upload' && !selectedFile) {
      toast({
        title: t('transcription.toast.fileRequired'),
        variant: 'destructive',
      });
      return;
    }

    if (sourceMode === 'sample' && !selectedSampleId) {
      toast({
        title: t('transcription.toast.sampleRequired'),
        variant: 'destructive',
      });
      return;
    }

    setIsTranscribing(true);
    setErrorMessage(null);

    try {
      const response = await apiClient.transcribeSubtitles({
        file: sourceMode === 'upload' ? selectedFile ?? undefined : undefined,
        sampleId: sourceMode === 'sample' ? selectedSampleId : undefined,
        language: language === 'auto' ? undefined : language,
        model,
      });
      setResult(response);
    } catch (error) {
      if (isPendingDownloadError(error)) {
        setDownloadingModelName(error.modelName ?? `whisper-${model}`);
        setErrorMessage(t('transcription.status.downloading'));
        toast({
          title: t('transcription.toast.downloading'),
          description: t('transcription.toast.downloadingDescription'),
        });
      } else {
        const message =
          error instanceof Error ? error.message : t('common.unknownError');
        setErrorMessage(message);
        toast({
          title: t('transcription.toast.failed'),
          description: message,
          variant: 'destructive',
        });
      }
    } finally {
      setIsTranscribing(false);
    }
  };

  const exportResult = async (format: 'txt' | 'srt' | 'vtt') => {
    if (!result) {
      return;
    }

    let content = '';
    let mimeType = 'text/plain;charset=utf-8';
    let filterName = 'Text';

    if (format === 'txt') {
      content = buildTxt(result);
      filterName = 'TXT';
    } else if (format === 'srt') {
      content = buildSrt(result);
      filterName = 'SRT';
    } else {
      content = buildVtt(result);
      mimeType = 'text/vtt;charset=utf-8';
      filterName = 'VTT';
    }

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const filename = `transcription-${timestamp}.${format}`;
    const blob = new Blob([content], { type: mimeType });

    try {
      await platform.filesystem.saveFile(filename, blob, [
        { name: filterName, extensions: [format] },
      ]);
    } catch (error) {
      toast({
        title: t('transcription.toast.exportFailed'),
        description:
          error instanceof Error ? error.message : t('common.unknownError'),
        variant: 'destructive',
      });
    }
  };

  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="mb-6 shrink-0">
        <h1 className="text-2xl font-bold">{t('transcription.title')}</h1>
        <p className="text-muted-foreground mt-1">{t('transcription.subtitle')}</p>
      </div>

      <div
        className={`grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-6 flex-1 min-h-0 ${
          isPlayerVisible ? BOTTOM_SAFE_AREA_PADDING : ''
        }`}
      >
        <Card className="flex flex-col min-h-0">
          <CardHeader>
            <CardTitle className="text-lg">{t('transcription.source.label')}</CardTitle>
            <CardDescription>{t('transcription.subtitle')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 overflow-y-auto">
            <div className="grid grid-cols-2 gap-2">
              <Button
                variant={sourceMode === 'upload' ? 'default' : 'outline'}
                onClick={() => setSourceMode('upload')}
              >
                {t('transcription.source.upload')}
              </Button>
              <Button
                variant={sourceMode === 'sample' ? 'default' : 'outline'}
                onClick={() => setSourceMode('sample')}
              >
                {t('transcription.source.sample')}
              </Button>
            </div>

            {sourceMode === 'upload' ? (
              <div className="space-y-2">
                <Label htmlFor="transcription-file">{t('transcription.upload.label')}</Label>
                <Input
                  id="transcription-file"
                  type="file"
                  accept="audio/*"
                  onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
                />
                <p className="text-xs text-muted-foreground">{t('transcription.upload.hint')}</p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label>{t('transcription.sample.profile')}</Label>
                  <Select value={selectedProfileId} onValueChange={setSelectedProfileId}>
                    <SelectTrigger>
                      <SelectValue placeholder={t('transcription.sample.emptyProfiles')} />
                    </SelectTrigger>
                    <SelectContent>
                      {profiles.map((profile) => (
                        <SelectItem key={profile.id} value={profile.id}>
                          {profile.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>{t('transcription.sample.sample')}</Label>
                  <Select value={selectedSampleId} onValueChange={setSelectedSampleId}>
                    <SelectTrigger>
                      <SelectValue placeholder={t('transcription.sample.emptySamples')} />
                    </SelectTrigger>
                    <SelectContent>
                      {samples.map((sample, index) => {
                        const sampleText = sample.reference_text.trim();
                        return (
                          <SelectItem key={sample.id} value={sample.id}>
                            {sampleText || t('transcription.sample.sampleLabel', { index: index + 1 })}
                          </SelectItem>
                        );
                      })}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            <div className="space-y-2">
              <Label>{t('transcription.options.language')}</Label>
              <Select
                value={language}
                onValueChange={(value) => setLanguage(value as LanguageSelection)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">{t('transcription.options.languageAuto')}</SelectItem>
                  {LANGUAGE_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>{t('transcription.options.model')}</Label>
              <Select value={model} onValueChange={(value) => setModel(value as WhisperModelSize)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {WHISPER_MODELS.map((whisperModel) => (
                    <SelectItem key={whisperModel} value={whisperModel}>
                      {whisperModel}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <Button className="w-full" onClick={runTranscription} disabled={isTranscribing}>
              {isTranscribing
                ? t('transcription.actions.transcribing')
                : t('transcription.actions.transcribe')}
            </Button>

            {errorMessage && (
              <p className="text-sm text-destructive">{errorMessage}</p>
            )}
          </CardContent>
        </Card>

        <Card className="flex flex-col min-h-0">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="text-lg">{t('transcription.result.title')}</CardTitle>
              {result && (
                <div className="flex items-center gap-2">
                  <Badge variant="outline">
                    {t('transcription.result.duration', {
                      seconds: result.duration.toFixed(2),
                    })}
                  </Badge>
                  <Badge variant="outline">
                    {t('transcription.result.segments', {
                      count: result.segments.length,
                    })}
                  </Badge>
                </div>
              )}
            </div>
            <div className="flex items-center gap-2 pt-1">
              <Button
                variant="outline"
                size="sm"
                disabled={!result}
                onClick={() => exportResult('txt')}
              >
                {t('transcription.export.txt')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!result}
                onClick={() => exportResult('srt')}
              >
                {t('transcription.export.srt')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!result}
                onClick={() => exportResult('vtt')}
              >
                {t('transcription.export.vtt')}
              </Button>
            </div>
          </CardHeader>
          <CardContent className="flex-1 min-h-0 overflow-hidden flex flex-col gap-4">
            {!result ? (
              <div className="h-full flex items-center justify-center text-muted-foreground text-sm border border-dashed rounded-md">
                {t('transcription.result.placeholder')}
              </div>
            ) : (
              <>
                <div className="space-y-2">
                  <Label>{t('transcription.result.text')}</Label>
                  <Textarea value={result.text} readOnly className="min-h-[140px] resize-none" />
                </div>

                <div className="flex-1 min-h-0 flex flex-col">
                  <Label className="mb-2">{t('transcription.result.segmentsTitle')}</Label>
                  <div className="flex-1 min-h-0 overflow-auto border rounded-md">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>#</TableHead>
                          <TableHead>Start</TableHead>
                          <TableHead>End</TableHead>
                          <TableHead>Text</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {result.segments.map((segment) => (
                          <TableRow key={segment.index}>
                            <TableCell>{segment.index + 1}</TableCell>
                            <TableCell>{formatSubtitleTimestamp(segment.start, '.')}</TableCell>
                            <TableCell>{formatSubtitleTimestamp(segment.end, '.')}</TableCell>
                            <TableCell>{segment.text}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
