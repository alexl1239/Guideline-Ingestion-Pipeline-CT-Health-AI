# #!/usr/bin/env python3
# """
# Interactive query script.

# Demonstrates RAG query pattern against the UCG database.
# """

# import sys
# from pathlib import Path

# # Add src to path
# sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# from config import DATABASE_PATH, EMBEDDING_MODEL_NAME
# from query_engine import RAGQueryEngine


# def mock_embedding_function(text: str):
#     """
#     Mock embedding function for demonstration.

#     Replace with real OpenAI call in production.
#     """
#     # TODO: Implement real OpenAI embedding
#     # from openai import OpenAI
#     # import os
#     # client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
#     # response = client.embeddings.create(
#     #     model=EMBEDDING_MODEL_NAME,
#     #     input=text
#     # )
#     # return response.data[0].embedding

#     # Mock return for demonstration
#     return [0.0] * 1536


# def interactive_query():
#     """Run interactive query loop."""
#     print("=" * 80)
#     print("UCG-23 RAG QUERY INTERFACE")
#     print("=" * 80)
#     print(f"Database: {DATABASE_PATH}")
#     print()

#     # Initialize query engine
#     engine = RAGQueryEngine(DATABASE_PATH, mock_embedding_function)

#     # Show database stats
#     try:
#         stats = engine.get_database_stats()
#         print(f"Database contains:")
#         print(f"  - {stats['document_count']} documents")
#         print(f"  - {stats['section_count']} sections")
#         print(f"  - {stats['parent_chunk_count']} parent chunks")
#         print(f"  - {stats['child_chunk_count']} child chunks")
#         print(f"  - {stats['embedded_chunk_count']} embedded chunks")
#     except Exception as e:
#         print(f"Warning: Could not load database stats: {e}")

#     print()
#     print("Enter your query (or 'quit' to exit):")
#     print("-" * 80)

#     while True:
#         query = input("\n> ").strip()

#         if query.lower() in ['quit', 'exit', 'q']:
#             print("Goodbye!")
#             break

#         if not query:
#             continue

#         try:
#             # Execute query
#             results = engine.query(query, top_k=3)

#             if not results:
#                 print("No results found.")
#                 continue

#             # Display results
#             print(f"\nFound {len(results)} relevant sections:")
#             print("-" * 80)

#             for i, result in enumerate(results, 1):
#                 print(f"\n{i}. {result['section_path']}")
#                 print(f"   Document: {result['document_title']} {result['document_version']}")
#                 print(f"   Pages: {result['page_start']}-{result['page_end']}")
#                 print(f"   Tokens: {result['token_count']}")
#                 print(f"   Relevance: {1 - result['distance']:.2%}")
#                 print(f"\n   Preview:")
#                 preview = result['content'][:400].replace('\n', '\n   ')
#                 print(f"   {preview}...")

#             # Optionally format for LLM
#             print("\n" + "=" * 80)
#             response = input("Format context for LLM? (y/n): ").strip().lower()
#             if response == 'y':
#                 context = engine.format_context_for_llm(results)
#                 print("\nFormatted Context:")
#                 print("-" * 80)
#                 print(context)

#         except Exception as e:
#             print(f"Error executing query: {e}")
#             import traceback
#             traceback.print_exc()


# def main():
#     """Run query interface."""
#     import argparse

#     parser = argparse.ArgumentParser(description="Query UCG-23 RAG database")
#     parser.add_argument("--query", type=str, help="Single query to execute")
#     parser.add_argument("--top-k", type=int, default=3, help="Number of results")
#     args = parser.parse_args()

#     if args.query:
#         # Single query mode
#         engine = RAGQueryEngine(DATABASE_PATH, mock_embedding_function)
#         results = engine.query(args.query, top_k=args.top_k)

#         for i, result in enumerate(results, 1):
#             print(f"\n{i}. {result['section_path']}")
#             print(f"   Pages: {result['page_start']}-{result['page_end']}")
#             print(f"   Preview: {result['content'][:200]}...")
#     else:
#         # Interactive mode
#         interactive_query()


# if __name__ == "__main__":
#     main()
