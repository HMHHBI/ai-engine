'use client';

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body className="flex h-screen w-full flex-col items-center justify-center bg-background px-4 text-center">
        <div className="max-w-md space-y-4">
          <h2 className="text-xl font-semibold tracking-tight text-foreground">
            Critical Application Error
          </h2>
          <p className="text-sm text-muted-foreground">
            The application encountered a critical runtime error.
          </p>
          <button
            onClick={() => reset()}
            className="inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow transition-colors hover:bg-primary/90"
          >
            Reload application
          </button>
        </div>
      </body>
    </html>
  );
}
