import { Skeleton } from "@/components/feedback/skeleton";

export function MessageSkeleton() {
  return (
    <div
      data-testid="message-skeleton"
      aria-hidden="true"
      className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-6 sm:px-6"
    >
      <div className="flex justify-end">
        <div className="flex max-w-[72%] flex-col items-end gap-2">
          <Skeleton className="h-4 w-32 rounded-full" />
          <Skeleton className="h-10 w-52 rounded-2xl" />
        </div>
      </div>

      <div className="flex justify-start">
        <div className="flex w-full max-w-[82%] flex-col gap-2.5">
          <Skeleton className="h-3 w-24 rounded-full" />
          <Skeleton className="h-4 w-full max-w-xl rounded" />
          <Skeleton className="h-4 w-11/12 max-w-lg rounded" />
          <Skeleton className="h-4 w-4/5 max-w-md rounded" />
        </div>
      </div>

      <div className="flex justify-end">
        <div className="flex max-w-[72%] justify-end">
          <Skeleton className="h-12 w-64 rounded-2xl" />
        </div>
      </div>
    </div>
  );
}
