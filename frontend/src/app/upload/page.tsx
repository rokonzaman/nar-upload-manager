"use client";

import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/page-header";
import { FileUploader } from "@/components/file-uploader";
import type { UploadResult } from "@/lib/types";

export default function UploadPage() {
  const queryClient = useQueryClient();

  const onUploaded = (results: UploadResult[]) => {
    const succeeded = results.filter((r) => r.success).length;
    const failed = results.length - succeeded;
    if (succeeded > 0) toast.success(`${succeeded} bundle(s) uploaded`);
    if (failed > 0) toast.error(`${failed} file(s) failed — see details below`);
    queryClient.invalidateQueries({ queryKey: ["bundles-grouped"] });
    queryClient.invalidateQueries({ queryKey: ["bundles-flat"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Upload NAR Bundles"
        description="Upload .nar files to the central repository — metadata and checksums are extracted automatically"
      />
      <div className="max-w-3xl">
        <FileUploader onUploaded={onUploaded} />
      </div>
    </div>
  );
}
