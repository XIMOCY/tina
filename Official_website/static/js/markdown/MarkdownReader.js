const File_Technical_Doc = "/static/src/Technical_Doc.md";
const Technical_Doc_Area = document.querySelector(".Technical_Doc");
const regex =
  /<code\s+class="[^"]*\blanguage-mermaid\b[^"]*">([\s\S]*?)<\/code>/gi;
class MarkdownReader {
  static parse(text, container) {
    container.innerHTML = "";
    let Orin = marked
      .parse(text)
      .replace(regex, '<div class="mermaid">$1</div>');
    container.innerHTML = Orin;
    MathJax.typeset();
    hljs.highlightAll();
    mermaid.init(undefined, ".mermaid");
  }
  static Urlparse(url, container) {
    fetch(url)
      .then((response) => response.text())
      .then((text) => {
        this.parse(text, container);
      });
  }
}