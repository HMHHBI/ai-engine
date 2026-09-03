import { Skeleton } from "@/components/feedback/skeleton";

export function MessageSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 py-6">
      {/* User message skeleton */}
      <div className="flex justify-end">
        <div className="flex max-w-[70%] flex-col items-end gap-2">
          <Skeleton className="h-10 w-48 rounded-2xl" />
        </div>
      </div>

      {/* AI message skeleton */}
      <div className="flex justify-start">
        <div className="flex max-w-[80%] flex-col gap-2.5">
          <Skeleton className="h-4 w-28 rounded-md" />
          <Skeleton className="h-4 w-72 rounded-md" />
          <Skeleton className="h-4 w-60 rounded-md" />
          <Skeleton className="h-4 w-44 rounded-md" />
        </div>
      </div>

      {/* Another User message skeleton */}
      <div className="flex justify-end">
        <div className="flex max-w-[70%] flex-col items-end gap-2">
          <Skeleton className="h-12 w-64 rounded-2xl" />
        </div>
      </div>
    </div>
  );
}
