import { describe, expect, it } from "vitest";
import {
  chunkFilesForRegistryImport,
  REGISTRY_IMPORT_BATCH_MAX_BYTES,
  REGISTRY_IMPORT_BATCH_MAX_FILES,
  registryImportBatchProgress,
} from "./api";

function mockFile(name: string, size: number): File {
  return new File([new Uint8Array(size)], name, { type: "image/jpeg" });
}

describe("chunkFilesForRegistryImport", () => {
  it("keeps a single small batch when under limits", () => {
    const files = [mockFile("a.jpg", 1000), mockFile("b.jpg", 2000)];
    const batches = chunkFilesForRegistryImport(files);
    expect(batches.length).toBe(1);
    expect(batches[0]?.length).toBe(2);
  });

  it("splits when cumulative size exceeds batch max", () => {
    const half = Math.floor(REGISTRY_IMPORT_BATCH_MAX_BYTES / 2);
    const files = [mockFile("a.jpg", half), mockFile("b.jpg", half), mockFile("c.jpg", half)];
    const batches = chunkFilesForRegistryImport(files);
    expect(batches.length).toBe(2);
    expect(batches[0]?.length).toBe(2);
    expect(batches[1]?.length).toBe(1);
  });

  it("isolates a file larger than batch max but within server max", () => {
    const big = REGISTRY_IMPORT_BATCH_MAX_BYTES + 1024;
    const small = 100;
    const files = [mockFile("big.jpg", big), mockFile("s.jpg", small)];
    const batches = chunkFilesForRegistryImport(files);
    expect(batches.length).toBe(2);
    expect(batches[0]?.length).toBe(1);
    expect(batches[0]?.[0]?.name).toBe("big.jpg");
    expect(batches[1]?.length).toBe(1);
  });

  it("starts a new batch when file count hits max", () => {
    const n = REGISTRY_IMPORT_BATCH_MAX_FILES + 5;
    const files = Array.from({ length: n }, (_, i) => mockFile(`f${i}.jpg`, 100));
    const batches = chunkFilesForRegistryImport(files);
    expect(batches.length).toBeGreaterThanOrEqual(2);
    expect(batches[0]?.length).toBe(REGISTRY_IMPORT_BATCH_MAX_FILES);
  });
});

describe("registryImportBatchProgress", () => {
  it("maps upload and poll phases across batches", () => {
    expect(registryImportBatchProgress(0, 2, "upload", 0, 0)).toBe(0);
    expect(registryImportBatchProgress(0, 2, "upload", 100, 0)).toBe(18);
    expect(registryImportBatchProgress(0, 2, "poll", 100, 0)).toBe(18);
    expect(registryImportBatchProgress(0, 2, "poll", 100, 100)).toBe(50);
    expect(registryImportBatchProgress(1, 2, "poll", 100, 100)).toBe(100);
  });
});
