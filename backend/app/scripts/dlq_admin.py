import argparse
import asyncio
import sys
from app.services.document_job_dlq import DocumentJobDLQService


async def main() -> None:
    parser = argparse.ArgumentParser(description="Administrative DLQ operator utility")
    parser.add_argument("action", choices=("redrive", "discard"))
    parser.add_argument("message_id", help="DLQ message ID in Redis Stream")
    args = parser.parse_args()

    if args.action == "redrive":
        new_id = await DocumentJobDLQService.redrive(dlq_message_id=args.message_id)
        if new_id:
            print(f"Successfully re-enqueued to active queue as: {new_id}")
            sys.exit(0)
        else:
            print(f"Failed to redrive message {args.message_id}")
            sys.exit(1)
    else:
        discarded = await DocumentJobDLQService.discard(dlq_message_id=args.message_id)
        if discarded:
            print(f"Successfully discarded DLQ message: {args.message_id}")
            sys.exit(0)
        else:
            print(f"Message {args.message_id} not found in DLQ")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
