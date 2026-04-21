/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DirectoryCheck } from './DirectoryCheck';
/**
 * Response model for filesystem health check.
 */
export type FilesystemHealthResponse = {
    healthy: boolean;
    disk_free_mb?: (number | null);
    disk_total_mb?: (number | null);
    directories: Array<DirectoryCheck>;
};

