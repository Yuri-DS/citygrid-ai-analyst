"""
RAG (Retrieval-Augmented Generation) module for CityGrid AI Analyst.

Uses sentence-transformers for embeddings and ChromaDB for vector storage.
"""

import os
from pathlib import Path
from typing import List, Optional
import hashlib

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document


# === Configuration ===

DEFAULT_DOCS_PATH = Path(__file__).parent.parent.parent / "docs_workspace"
DEFAULT_CHROMA_PATH = Path(__file__).parent.parent.parent / "data" / "chroma_db"

# Embedding model - small and fast, good quality
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Text splitting parameters
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


class RAGSystem:
    """
    RAG system for document retrieval.
    
    Loads documents, creates embeddings, stores in ChromaDB,
    and provides search functionality.
    """
    
    def __init__(
        self,
        docs_path: Path = DEFAULT_DOCS_PATH,
        chroma_path: Path = DEFAULT_CHROMA_PATH,
        embedding_model: str = EMBEDDING_MODEL,
    ):
        self.docs_path = Path(docs_path)
        self.chroma_path = Path(chroma_path)
        self.embedding_model_name = embedding_model
        
        # Initialize embeddings
        print(f"Loading embedding model: {embedding_model}...")
        self.embeddings = HuggingFaceEmbeddings(
            model_name=embedding_model,
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        
        # Vector store (lazy initialization)
        self._vector_store: Optional[Chroma] = None
    
    @property
    def vector_store(self) -> Chroma:
        """Get or create vector store."""
        if self._vector_store is None:
            self._vector_store = self._load_or_create_store()
        return self._vector_store
    
    def _load_or_create_store(self) -> Chroma:
        """Load existing store or create new one."""
        # Check if store exists
        if self.chroma_path.exists() and any(self.chroma_path.iterdir()):
            print(f"Loading existing vector store from {self.chroma_path}")
            return Chroma(
                persist_directory=str(self.chroma_path),
                embedding_function=self.embeddings
            )
        
        # Create new store
        print("Creating new vector store...")
        return self._create_store()
    
    def _create_store(self) -> Chroma:
        """Create new vector store from documents."""
        # Load documents
        documents = self._load_documents()
        
        if not documents:
            print("Warning: No documents found!")
            # Create empty store
            return Chroma(
                persist_directory=str(self.chroma_path),
                embedding_function=self.embeddings
            )
        
        # Split documents
        chunks = self._split_documents(documents)
        print(f"Created {len(chunks)} chunks from {len(documents)} documents")
        
        # Create vector store
        self.chroma_path.mkdir(parents=True, exist_ok=True)
        
        vector_store = Chroma.from_documents(
            documents=chunks,
            embedding=self.embeddings,
            persist_directory=str(self.chroma_path)
        )
        
        print(f"Vector store created at {self.chroma_path}")
        return vector_store
    
    def _load_documents(self) -> List[Document]:
        """Load all markdown documents from docs_workspace."""
        if not self.docs_path.exists():
            print(f"Warning: Documents path does not exist: {self.docs_path}")
            return []
        
        documents = []
        
        # Load all .md files
        for md_file in self.docs_path.glob("*.md"):
            try:
                loader = TextLoader(str(md_file), encoding='utf-8')
                docs = loader.load()
                
                # Add source metadata
                for doc in docs:
                    doc.metadata['source'] = md_file.name
                    doc.metadata['file_path'] = str(md_file)
                
                documents.extend(docs)
                print(f"Loaded: {md_file.name}")
            except Exception as e:
                print(f"Error loading {md_file}: {e}")
        
        return documents
    
    def _split_documents(self, documents: List[Document]) -> List[Document]:
        """Split documents into chunks."""
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            length_function=len,
            separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""]
        )
        
        return splitter.split_documents(documents)
    
    def search(self, query: str, k: int = 5) -> List[Document]:
        """
        Search for relevant documents.
        
        Args:
            query: Search query
            k: Number of results to return
            
        Returns:
            List of relevant Document objects
        """
        return self.vector_store.similarity_search(query, k=k)
    
    def search_with_scores(self, query: str, k: int = 5) -> List[tuple[Document, float]]:
        """
        Search with relevance scores.
        
        Args:
            query: Search query
            k: Number of results to return
            
        Returns:
            List of (Document, score) tuples
        """
        return self.vector_store.similarity_search_with_score(query, k=k)
    
    def rebuild_store(self) -> None:
        """Rebuild vector store from scratch."""
        # Delete existing store
        if self.chroma_path.exists():
            import shutil
            shutil.rmtree(self.chroma_path)
            print(f"Deleted existing store at {self.chroma_path}")
        
        # Recreate
        self._vector_store = self._create_store()
    
    def get_stats(self) -> dict:
        """Get statistics about the vector store."""
        collection = self.vector_store._collection
        return {
            "total_documents": collection.count(),
            "docs_path": str(self.docs_path),
            "chroma_path": str(self.chroma_path),
            "embedding_model": self.embedding_model_name,
        }


# === Global instance ===

_rag_system: Optional[RAGSystem] = None


def get_rag_system(
    docs_path: Optional[Path] = None,
    chroma_path: Optional[Path] = None,
) -> RAGSystem:
    """Get or create RAG system instance."""
    global _rag_system
    
    if _rag_system is None:
        _rag_system = RAGSystem(
            docs_path=docs_path or DEFAULT_DOCS_PATH,
            chroma_path=chroma_path or DEFAULT_CHROMA_PATH,
        )
    
    return _rag_system


def search_docs(query: str, k: int = 5) -> List[Document]:
    """Convenience function to search documents."""
    return get_rag_system().search(query, k=k)
