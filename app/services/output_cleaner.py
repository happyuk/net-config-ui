import re

_BACKSPACE_CLEAN = re.compile(r".\x08")
_NONPRINTABLE = re.compile(r"[^\x09\x0A\x0D\x20-\x7E]")  # allow \t, \n, \r
_ANSI_ESCAPES = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
_CISCO_WRAP = re.compile(r"\$")   # Cisco uses $ when wrapping templates
_MULTI_BLANK = re.compile(r"\n\s*\n+")

# Helper function to sanitise network device CLI text by removing backspaces, ANSI code
# and other non-rointale characters and artifacts
def clean_output(text: str) -> str:
    # 1. Remove IOS backspace erasures
    while True:
        new = _BACKSPACE_CLEAN.sub("", text)
        if new == text:
            break
        text = new

    # 2. Remove ANSI escape codes
    text = _ANSI_ESCAPES.sub("", text)

    # 3. Remove non-printable characters
    text = _NONPRINTABLE.sub("", text)

    # 4. Remove Cisco wrapped-line artifacts ('$')
    text = _CISCO_WRAP.sub("", text)

    # 5. Collapse multiple blank lines
    text = _MULTI_BLANK.sub("\n", text)

    return text.strip()