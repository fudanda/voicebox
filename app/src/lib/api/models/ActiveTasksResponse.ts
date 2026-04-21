/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ActiveDownloadTask } from './ActiveDownloadTask';
import type { ActiveGenerationTask } from './ActiveGenerationTask';
/**
 * Response model for active tasks.
 */
export type ActiveTasksResponse = {
    downloads: Array<ActiveDownloadTask>;
    generations: Array<ActiveGenerationTask>;
};

