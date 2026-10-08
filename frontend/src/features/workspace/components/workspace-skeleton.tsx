import { Skeleton } from "@/components/feedback/skeleton";

export function WorkspaceSkeleton() {
  return (
    <div
      data-testid="workspace-skeleton"
      aria-hidden="true"
      className="flex min-h-0 flex-1 overflow-hidden bg-background"
    >
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="shrink-0 border-b border-border px-4 py-2.5 sm:px-5">
          <div className="mx-auto flex w-full max-w-3xl items-center gap-3">
            <Skeleton className="size-8 shrink-0 rounded-lg" />

            <div className="min-w-0 flex-1 space-y-1.5">
              <Skeleton className="h-2.5 w-20 rounded" />
              <Skeleton className="h-4 w-48 max-w-full rounded" />
            </div>

            <Skeleton className="hidden h-3 w-16 shrink-0 rounded sm:block" />
            <Skeleton className="h-6 w-20 shrink-0 rounded-full" />
          </div>
        </div>

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <div className="flex-1 overflow-hidden">
            <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6 sm:px-6 sm:py-8">
              <div className="flex justify-end">
                <Skeleton className="h-10 w-48 rounded-2xl" />
              </div>

              <div className="flex justify-start">
                <div className="w-full max-w-[80%] space-y-2.5">
                  <Skeleton className="h-3 w-24 rounded" />
                  <Skeleton className="h-4 w-full max-w-xl rounded" />
                  <Skeleton className="h-4 w-5/6 max-w-lg rounded" />
                  <Skeleton className="h-4 w-2/3 max-w-md rounded" />
                </div>
              </div>

              <div className="flex justify-end">
                <Skeleton className="h-12 w-64 rounded-2xl" />
              </div>
            </div>
          </div>

          <div className="border-t border-border bg-background">
            <div className="mx-auto flex w-full max-w-3xl items-center justify-end px-2.5 pb-2 sm:px-4">
              <Skeleton className="h-7 w-28 rounded-lg" />
            </div>
          </div>

          <div className="px-2.5 pb-2.5 sm:px-4 sm:pb-4">
            <div className="mx-auto w-full max-w-3xl">
              <Skeleton className="h-24 w-full rounded-2xl" />
            </div>
          </div>
        </div>
      </div>

      <div className="hidden w-[38%] min-w-[320px] max-w-[520px] border-l border-border lg:flex lg:flex-col">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <Skeleton className="h-4 w-28 rounded" />
          <Skeleton className="size-7 rounded-lg" />
        </div>

        <div className="flex-1 space-y-4 p-4">
          <Skeleton className="h-4 w-3/4 rounded" />
          <Skeleton className="h-3 w-full rounded" />
          <Skeleton className="h-3 w-5/6 rounded" />
          <Skeleton className="h-3 w-4/6 rounded" />
          <Skeleton className="mt-6 h-64 w-full rounded-xl" />
        </div>
      </div>
    </div>
  );
}
