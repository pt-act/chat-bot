import logging

from db.vector import get_vectorstore

logger = logging.getLogger(__name__)


def retrieve_context(state):
    question = state["question"]

    # What is MMR (Maximal Marginal Relevance)?
    # Normal similarity search returns the top-3 most similar chunks. Problem: if your policy doc repeats the same paragraph 3 times, you get 3 nearly identical chunks — wasted context.
    # MMR fetches 10 candidates then picks 3 that are both relevant AND different from each other. More information per token sent to the LLM.
    
    # MMR: fetch 10 candidates, return the 3 most relevant AND diverse
    # Without MMR: top-3 similarity can return 3 near-identical chunks (wasted context)
    # With MMR: picks chunks that cover different parts of the answer
    docs = get_vectorstore().max_marginal_relevance_search(
        question,
        k=3,        # how many chunks to return to the LLM
        fetch_k=10  # how many candidates to consider before picking
    )

    context = "\n\n".join(d.page_content for d in docs)

    # collect unique source file names so we know which docs answered this question
    sources = list({d.metadata.get("source_file", "unknown") for d in docs})

    logger.info("Retrieved %d chunks from %s", len(docs), sources)
    return {"docs": context, "sources": sources}
