from app.agents.verifier_numeric import NumericVerifierWork
from app.agents.literature_suggester import LiteratureSuggesterWork
from app.work import AgentWork
from app.agents.literature_suggester import suggest_literature
from app.agents.verifier_lean import verify_lean
from app.agents.verifier_numeric import verify_numeric, setup_executor
from app.graphtools import make_graph_request
from app.agents.doc_ingester import ingest_document
import asyncio

# this one's intended to be manually run, not pytest
# literature guide 
async def check_literature():
    work = LiteratureSuggesterWork()
    task = "functional inequality f(x+y)f(x-y) ≥ f(x)^2 - f(y)^2 implies sign-definiteness. Find known proofs or approaches for showing function has constant sign or 0 under strictness. Provide references or sketches."
    res = await suggest_literature(task, work)
    print (f"\n\n FINAL FOR LIT: {res}")

async def check_verifier_lean():
    task = """
    Lemma sign_from_f0_nonzero (f : ℝ → ℝ) (H : ∀ x y : ℝ, f (x + y) * f (x - y) ≥ f x ^ 2 - f y ^ 2) : (f 0 ≠ 0 → ((f 0 > 0 → ∀ x, f x ≥ 0) ∧ (f 0 < 0 → ∀ x, f x ≤ 0))).
Proof sketch: assume f0 ≠ 0. For arbitrary x, specialize H x x to get f (2*x) * f 0 ≥ 0. If f 0 > 0 then for all x, f (2*x) ≥ 0, and by substituting z = 2*x (which ranges over ℝ) deduce ∀ z, f z ≥ 0. Similarly if f 0 < 0 deduce ∀ z, f z ≤ 0. Complete formalization in Lean with basic arithmetic and inequalities.
    """

    work = AgentWork()
    res = await verify_lean(task, "No context.", work)
    print (f"\n\n FINAL FOR LEAN: {res}")

async def check_verifier_sympy():
    task = """
    Verify equality: \\int \\frac{1}{(x^2 + 1)^2} \\, dx = \\frac{1}{2} \\left( \\frac{x}{x^2 + 1} + \\arctan(x) \\right) + C
    """
    work = NumericVerifierWork()
    res = await verify_numeric(task, "No context", work)
    print (f"\n\n FINAL FOR SYMPY VERIFIER: {res}")

async def check_result_of_query():

    premises_ids = ["if_sequence_definition_then_closed_form_Ak_Bk"]
    cypher_q = """
    MATCH (s:Statement)
    WHERE s.uid IN $ids
    RETURN s.uid AS uid, s.verification AS verification
    """
    result = make_graph_request(
        endpoint="/graph/query",
        body=cypher_q.replace("$ids", str(premises_ids)) # DEFINITELY inSECURE
    )

    print(result)


if __name__ == "__main__":
    setup_executor()
    asyncio.run(check_result_of_query())