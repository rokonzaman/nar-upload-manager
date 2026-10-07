"use client";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { Page } from "@/lib/types";

export interface Column<T> {
  key: string;
  header: React.ReactNode;
  cell: (item: T) => React.ReactNode;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[] | undefined;
  loading?: boolean;
  page?: Page<T>;
  onPageChange?: (page: number) => void;
  rowKey: (item: T) => string | number;
  emptyState?: React.ReactNode;
  selectedIds?: Set<number>;
  onSelectRow?: (id: number, checked: boolean) => void;
}

export function DataTable<T>({
  columns,
  data,
  loading,
  page,
  onPageChange,
  rowKey,
  emptyState,
}: DataTableProps<T>) {
  if (!loading && data && data.length === 0 && emptyState) {
    return <>{emptyState}</>;
  }
  return (
    <div className="space-y-3">
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((col) => (
                <TableHead key={col.key} className={col.className}>
                  {col.header}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading
              ? Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    {columns.map((col) => (
                      <TableCell key={col.key}>
                        <Skeleton className="h-5 w-full max-w-[140px]" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              : data?.map((item) => (
                  <TableRow key={rowKey(item)}>
                    {columns.map((col) => (
                      <TableCell key={col.key} className={col.className}>
                        {col.cell(item)}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      </div>
      {page && onPageChange && page.pages > 1 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {page.total} items — page {page.page} of {page.pages}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page.page <= 1}
              onClick={() => onPageChange(page.page - 1)}
            >
              <ChevronLeft className="h-4 w-4" /> Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page.page >= page.pages}
              onClick={() => onPageChange(page.page + 1)}
            >
              Next <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
