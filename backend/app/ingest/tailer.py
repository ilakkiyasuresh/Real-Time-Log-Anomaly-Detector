import asyncio
import os


async def tail(path: str, from_start: bool = False, poll: float = 0.2):
    """Yield complete lines appended to `path`, forever.

    Handles: file not existing yet, log rotation (file replaced -> new inode),
    truncation (file shrinks), and half-written lines (waits for the newline).
    """
    while not os.path.exists(path):
        await asyncio.sleep(poll)

    f = open(path, "r", encoding="utf-8", errors="replace")
    inode = os.fstat(f.fileno()).st_ino
    if not from_start:
        f.seek(0, os.SEEK_END)

    partial = ""
    while True:
        line = f.readline()
        if line:
            partial += line
            if partial.endswith("\n"):
                yield partial.rstrip("\r\n")
                partial = ""
            continue  # keep reading while there is data

        # No new data: check for rotation or truncation before sleeping.
        try:
            st = os.stat(path)
        except FileNotFoundError:          # mid-rotation: new file not there yet
            await asyncio.sleep(poll)
            continue
        if st.st_ino != inode or st.st_size < f.tell():
            f.close()
            f = open(path, "r", encoding="utf-8", errors="replace")
            inode = os.fstat(f.fileno()).st_ino
            partial = ""
            continue
        await asyncio.sleep(poll)
