/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { StoryItemDetail } from './StoryItemDetail';
/**
 * Response model for story with items.
 */
export type StoryDetailResponse = {
    id: string;
    name: string;
    description: (string | null);
    created_at: string;
    updated_at: string;
    items?: Array<StoryItemDetail>;
};

