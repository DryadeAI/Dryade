"""RAG Command Handler - Search knowledge base with semantic search.

Target: ~80 LOC
"""

import logging
from typing import Any

from core.commands.protocol import Command

logger = logging.getLogger(__name__)

class RAGCommand(Command):
    """Command to search knowledge base via RAG agent.

    Usage: /rag query="your search query" [top_k=5] [collection="collection_name"]
    """

    def get_name(self) -> str:
        """Return command name."""
        return "rag"

    def get_description(self) -> str:
        """Return command description."""
        return "Search knowledge base with semantic search"

    def get_schema(self) -> dict[str, Any] | None:
        """Return argument schema."""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for knowledge base",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default: 5)",
                    "default": 5,
                },
                "collection": {
                    "type": "string",
                    "description": "Override collection name (optional)",
                },
            },
            "required": ["query"],
        }

    async def execute(self, args: dict[str, Any], context: dict[str, Any]) -> Any:
        """Execute RAG search.

        Args:
            args: Must contain 'query', optionally 'top_k' and 'collection'
            context: Execution context with user_id, conversation_id

        Returns:
            Search results with citations

        Raises:
            ValueError: If query is missing
        """
        from core.agents.rag_agent import RAGAgent

        query = args.get("query")
        if not query:
            raise ValueError("Missing required argument: query")

        top_k = args.get("top_k", 5)
        collection = args.get("collection")

        logger.info(f"Executing /rag command: query={query[:30]}..., user={context.get('user_id')}")

        # Create RAGAgent instance
        agent = RAGAgent()

        # Build context with optional overrides
        agent_context = {"top_k": top_k}
        if collection:
            agent_context["collection"] = collection

        # Execute search
        result = await agent.execute(query, agent_context)

        # Format response with citation
        if result.status == "error":
            return {
                "status": "error",
                "command": "rag",
                "error": result.error,
            }

        # Check for fallback (no results)
        if result.result and result.result.get("fallback"):
            return {
                "status": "ok",
                "command": "rag",
                "message": result.result["message"],
                "documents": [],
                "retrieved_count": 0,
            }

        # Format successful results with citations
        documents = result.result.get("documents", [])
        formatted_docs = []

        for i, doc in enumerate(documents, 1):
            formatted_docs.append(
                {
                    "citation": f"[{i}]",
                    "content": doc["content"],
                    "score": round(doc["score"], 3),
                    "source": doc.get("metadata", {}).get("source_id", "unknown"),
                }
            )

        return {
            "status": "ok",
            "command": "rag",
            "query": query,
            "documents": formatted_docs,
            "retrieved_count": len(formatted_docs),
        }
