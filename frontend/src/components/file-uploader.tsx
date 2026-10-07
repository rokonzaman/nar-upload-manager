"use client";

import { useCallback, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { uploadFiles } from "@/lib/api";
import type { UploadResult } from "@/lib/types";
import { formatBytes, cn } from "@/lib/utils";
import { CheckCircle2, FileArchive, UploadCloud, XCircle, X } from "lucide-react";

interface FileUploaderProps {
  onUploaded: (results: UploadResult[]) => void;
}

interface QueuedFile {
  file: File;
  progress: number;
  status: "queued" | "uploading" | "done" | "error";
  result?: UploadResult;
}

export function FileUploader({ onUploaded }: FileUploaderProps) {
  const [queue, setQueue] = useState<QueuedFile[]>([]);
  const [replace, setReplace] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const addFiles = useCallback((files: FileList | File[]) => {
    const incoming = Array.from(files).map((file) => ({
      file,
      progress: 0,
      status: "queued" as const,
    }));
    setQueue((prev) => [...prev, ...incoming]);
  }, []);

  const removeFile = (index: number) => setQueue((prev) => prev.filter((_, i) => i !== index));

  const startUpload = async () => {
    const pending = queue.filter((q) => q.status === "queued");
    if (pending.length === 0) return;
    setUploading(true);
    setQueue((prev) => prev.map((q) => (q.status === "queued" ? { ...q, status: "uploading" } : q)));
    try {
      const results = await uploadFiles(
        "/bundles/upload",
        pending.map((p) => p.file),
        { replace: String(replace) },
        (percent) => {
          setQueue((prev) => prev.map((q) => (q.status === "uploading" ? { ...q, progress: percent } : q)));
        },
      );
      setQueue((prev) =>
        prev.map((q) => {
          if (q.status !== "uploading") return q;
          const result = results.find((r) => r.filename === q.file.name);
          return {
            ...q,
            progress: 100,
            status: result?.success ? "done" : "error",
            result,
          };
        }),
      );
      onUploaded(results);
    } catch (error) {
      setQueue((prev) =>
        prev.map((q) =>
          q.status === "uploading"
            ? { ...q, status: "error", result: { filename: q.file.name, success: false, bundle: null, error: (error as Error).message, replaced: false } }
            : q,
        ),
      );
    } finally {
      setUploading(false);
    }
  };

  const queuedCount = queue.filter((q) => q.status === "queued").length;

  return (
    <div className="space-y-4">
      <Card
        className={cn(
          "border-2 border-dashed transition-colors cursor-pointer",
          dragging ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-primary/50",
        )}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          addFiles(e.dataTransfer.files);
        }}
      >
        <CardContent className="flex flex-col items-center justify-center py-12 text-center">
          <UploadCloud className="h-12 w-12 text-muted-foreground mb-4" />
          <p className="text-lg font-medium">Drag &amp; drop NAR files here</p>
          <p className="text-sm text-muted-foreground mt-1">or click to browse — multiple files supported</p>
          <input
            ref={inputRef}
            type="file"
            accept=".nar"
            multiple
            className="hidden"
            onChange={(e) => e.target.files && addFiles(e.target.files)}
          />
        </CardContent>
      </Card>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Switch id="replace" checked={replace} onCheckedChange={setReplace} />
          <Label htmlFor="replace">Replace existing versions</Label>
        </div>
        <Button onClick={startUpload} disabled={queuedCount === 0 || uploading}>
          <FileArchive className="h-4 w-4" />
          Upload {queuedCount > 0 ? `${queuedCount} file${queuedCount > 1 ? "s" : ""}` : ""}
        </Button>
      </div>

      {queue.length > 0 && (
        <div className="space-y-2">
          {queue.map((item, index) => (
            <div key={`${item.file.name}-${index}`} className="flex items-center gap-3 rounded-md border p-3">
              <FileArchive className="h-5 w-5 text-muted-foreground shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium truncate">{item.file.name}</p>
                  <span className="text-xs text-muted-foreground shrink-0">{formatBytes(item.file.size)}</span>
                </div>
                {item.status === "uploading" && <Progress value={item.progress} className="mt-2" />}
                {item.status === "done" && item.result?.bundle && (
                  <p className="text-xs text-emerald-500 mt-1 flex items-center gap-1">
                    <CheckCircle2 className="h-3 w-3" />
                    {item.result.bundle.bundle_group}:{item.result.bundle.artifact}:{item.result.bundle.version}
                    {item.result.replaced && " (replaced)"}
                  </p>
                )}
                {item.status === "error" && (
                  <p className="text-xs text-red-500 mt-1 flex items-center gap-1">
                    <XCircle className="h-3 w-3" /> {item.result?.error ?? "Upload failed"}
                  </p>
                )}
              </div>
              {item.status === "queued" && (
                <Button variant="ghost" size="icon" onClick={() => removeFile(index)}>
                  <X className="h-4 w-4" />
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
