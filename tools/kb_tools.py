"""Knowledge Base tools for querying Bedrock KB"""
import logging
import os
import boto3
from strands.tools import tool

logger = logging.getLogger(__name__)

# Lazy-initialized client (avoids creating boto3 client at import time)
_bedrock_agent_client = None


def _get_client():
    global _bedrock_agent_client
    if _bedrock_agent_client is None:
        _bedrock_agent_client = boto3.client(
            'bedrock-agent-runtime',
            region_name=os.getenv('AWS_REGION')
        )
    return _bedrock_agent_client


@tool
def search_knowledge_base(query: str, max_results: int = 5) -> str:
    """
    Search the Bedrock Knowledge Base for network architecture documentation.

    Use this to find information about network topology, subnet design, CIDR
    allocations, routing policies, security group design intent, and expected
    traffic flows.

    Args:
        query: Natural language search query
        max_results: Maximum number of results to return (default: 5)

    Returns:
        Formatted search results with source citations
    """
    kb_id = os.getenv('KNOWLEDGE_BASE_ID')
    if not kb_id:
        logger.warning("KNOWLEDGE_BASE_ID not configured")
        return "Knowledge base search unavailable: KNOWLEDGE_BASE_ID environment variable is not set."

    client = _get_client()

    try:
        response = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={'text': query},
            retrievalConfiguration={
                'vectorSearchConfiguration': {'numberOfResults': max_results}
            }
        )

        results = response.get('retrievalResults', [])
        if not results:
            return f"No results found for: {query}"

        formatted = []
        for i, result in enumerate(results, 1):
            content = result.get('content', {}).get('text', 'No content available')
            score = result.get('score', 0)

            # Extract source location (S3 URI or fallback)
            location = result.get('location', {})
            source_type = location.get('type', 'UNKNOWN')
            if source_type == 'S3':
                source = location.get('s3Location', {}).get('uri', 'Unknown S3 source')
            else:
                source = f"Source type: {source_type}"

            # Truncate very long chunks for readability
            if len(content) > 800:
                content = content[:800] + "..."

            formatted.append(
                f"Result {i} (relevance: {score:.2f})\n"
                f"Source: {source}\n"
                f"Content: {content}"
            )

        return "\n---\n".join(formatted)

    except client.exceptions.ResourceNotFoundException:
        logger.error(f"Knowledge base not found: {kb_id}")
        return f"Error: Knowledge base '{kb_id}' not found. Verify the ID is correct."
    except client.exceptions.ValidationException as e:
        logger.error(f"Validation error: {e}")
        return f"Error: Invalid search request - {str(e)}"
    except Exception as e:
        logger.error(f"Error searching knowledge base: {e}")
        return f"Error searching knowledge base: {str(e)}"


# Keep backward-compatible function for any direct callers
def query_knowledge_base(query: str, kb_id: str = None, max_results: int = 5) -> str:
    """Backward-compatible wrapper around search_knowledge_base."""
    if kb_id:
        os.environ['KNOWLEDGE_BASE_ID'] = kb_id
    return search_knowledge_base(query, max_results)
