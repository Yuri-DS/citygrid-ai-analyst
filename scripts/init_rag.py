"""
Initialize RAG system - build vector store from documents.

Run this script once after adding/updating documents in docs_workspace.

Usage:
    python scripts/init_rag.py
    python scripts/init_rag.py --rebuild  # Force rebuild
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rag import get_rag_system


def main():
    parser = argparse.ArgumentParser(description="Initialize RAG system")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild vector store")
    args = parser.parse_args()
    
    print("=" * 50)
    print("CityGrid RAG Initialization")
    print("=" * 50)
    
    # Get RAG system (this will create/load the store)
    rag = get_rag_system()
    
    if args.rebuild:
        print("\nRebuilding vector store...")
        rag.rebuild_store()
    
    # Print stats
    stats = rag.get_stats()
    print(f"\n{'=' * 50}")
    print("RAG System Stats:")
    print(f"  Documents indexed: {stats['total_documents']}")
    print(f"  Docs path: {stats['docs_path']}")
    print(f"  Chroma path: {stats['chroma_path']}")
    print(f"  Embedding model: {stats['embedding_model']}")
    print(f"{'=' * 50}")
    
    # Test search
    print("\nTest search: 'districts table columns'")
    results = rag.search("districts table columns", k=2)
    for i, doc in enumerate(results):
        print(f"\nResult {i+1} (from {doc.metadata.get('source', 'unknown')}):")
        print(doc.page_content[:300] + "...")
    
    print("\n✅ RAG system initialized successfully!")


if __name__ == "__main__":
    main()
