"""文档加载：支持 PDF / Markdown / docx / 纯文本。"""
from pathlib import Path
from typing import List

from langchain_core.documents import Document


class DocumentLoader:
    """按文件后缀分发到对应解析器，返回 LangChain Document 列表。"""

    SUPPORTED = {".pdf", ".md", ".markdown", ".txt", ".docx"}

    def load(self, file_path: str | Path) -> List[Document]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        if path.suffix.lower() not in self.SUPPORTED:
            raise ValueError(f"不支持的文件类型: {path.suffix}")

        loader = self._dispatch(path)
        docs = loader.load()
        # 统一写入来源元信息
        for d in docs:
            d.metadata.setdefault("source", str(path.name))
        return docs

    def load_dir(self, dir_path: str | Path) -> List[Document]:
        dir_path = Path(dir_path)
        docs: List[Document] = []
        for p in sorted(dir_path.rglob("*")):
            if p.is_file() and p.suffix.lower() in self.SUPPORTED:
                docs.extend(self.load(p))
        return docs

    def _dispatch(self, path: Path):
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            from langchain_community.document_loaders import PyPDFLoader
            return PyPDFLoader(str(path))
        if suffix in {".md", ".markdown"}:
            from langchain_community.document_loaders import TextLoader
            return TextLoader(str(path), encoding="utf-8")
        if suffix == ".docx":
            from langchain_community.document_loaders import Docx2txtLoader
            return Docx2txtLoader(str(path))
        # 默认按文本处理
        from langchain_community.document_loaders import TextLoader
        return TextLoader(str(path), encoding="utf-8")
