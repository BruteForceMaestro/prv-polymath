from app.agents.literature_suggester import suggest_literature
from app.agents.verifier_lean import verify_lean
from app.agents.verifier_numeric import verify_numeric, setup_executor
import asyncio

# this one's intended to be manually run, not pytest
# literature guide 
async def check_literature():
    task = "functional inequality f(x+y)f(x-y) ≥ f(x)^2 - f(y)^2 implies sign-definiteness. Find known proofs or approaches for showing function has constant sign or 0 under strictness. Provide references or sketches."
    res = await suggest_literature(task)
    print (f"\n\n FINAL FOR LIT: {res}")

async def check_verifier_lean():
    task = """
    Lemma sign_from_f0_nonzero (f : ℝ → ℝ) (H : ∀ x y : ℝ, f (x + y) * f (x - y) ≥ f x ^ 2 - f y ^ 2) : (f 0 ≠ 0 → ((f 0 > 0 → ∀ x, f x ≥ 0) ∧ (f 0 < 0 → ∀ x, f x ≤ 0))).
Proof sketch: assume f0 ≠ 0. For arbitrary x, specialize H x x to get f (2*x) * f 0 ≥ 0. If f 0 > 0 then for all x, f (2*x) ≥ 0, and by substituting z = 2*x (which ranges over ℝ) deduce ∀ z, f z ≥ 0. Similarly if f 0 < 0 deduce ∀ z, f z ≤ 0. Complete formalization in Lean with basic arithmetic and inequalities.
    """
    res = await verify_lean(task)
    print (f"\n\n FINAL FOR LEAN: {res}")

async def check_verifier_sympy():
    task = """
    Verify equality: \\int \\frac{1}{(x^2 + 1)^2} \\, dx = \\frac{1}{2} \\left( \\frac{x}{x^2 + 1} + \\arctan(x) \\right) + C
    """
    res = await verify_numeric(task)
    print (f"\n\n FINAL FOR SYMPY VERIFIER: {res}")



if __name__ == "__main__":
    setup_executor()
    asyncio.run(check_literature())