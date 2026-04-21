/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TranscriptionSegment } from './TranscriptionSegment';
/**
 * Response model for transcription with subtitle segments.
 */
export type TranscriptionSubtitlesResponse = {
    text: string;
    duration: number;
    segments: Array<TranscriptionSegment>;
};

