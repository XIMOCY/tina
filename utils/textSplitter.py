
class TextSplitter:
    def __init__(self):
        pass
    def split_text(self, text, max_length,splitter="\n\n"):
        """
        Split the text into smaller chunks of max_length    
        """
        chunks = []
        chunk = ""
        for line in text.split(splitter):
            if len(chunk) + len(line) > max_length:
                chunks.append(chunk)
                chunk = line
            else:
                chunk += line
        chunks.append(chunk)
        return chunks