"""Prompt templates for the LLM-as-judge."""

EXTRACTION_JUDGE_PROMPT = """\
You are evaluating the quality of a receipt data extraction performed by an AI model.

## Extracted Data
{extraction_json}

## Evaluation Criteria

Evaluate each criterion and return a structured verdict.

1. **validity** — Is `is_valid_receipt` correctly set? (True for receipts, False for non-receipts)
2. **merchant** — Is the merchant name present and plausible?
3. **arithmetic** — Does subtotal + tax + tip ≈ total? Do line item totals sum to ≈ subtotal?
4. **completeness** — Are all visible fields extracted (date, payment method, line items)?
5. **category** — Is the category appropriate for this merchant/purchase?

Score each criterion as pass/fail with a brief reason.
Give an overall_score from 1-10 (7+ = passed).
"""

EXTRACTION_JUDGE_WITH_GROUND_TRUTH_PROMPT = """\
You are evaluating the quality of a receipt data extraction performed by an AI model.

## Extracted Data
{extraction_json}

## Expected (Ground Truth)
{ground_truth_json}

## Evaluation Criteria

Compare the extraction to the ground truth and evaluate:

1. **validity** — `is_valid_receipt` matches ground truth
2. **merchant** — Merchant name matches (allow minor spelling differences)
3. **arithmetic** — Totals are mathematically consistent
4. **completeness** — Key fields (date, total, category) are present
5. **category** — Category matches ground truth (or is equally appropriate)

Score each criterion as pass/fail with a brief reason.
Give an overall_score from 1-10 (7+ = passed).
"""

EXTRACTION_JUDGE_WITH_IMAGE_PROMPT = """\
You are evaluating the quality of a receipt data extraction performed by an AI model.
You will see the original receipt image and the extracted data. Judge whether the extraction
accurately reflects what is shown in the image.

## Extracted Data
{extraction_json}

## Evaluation Criteria

1. **validity** — Is `is_valid_receipt` correct given the image?
2. **merchant** — Does the merchant name match what's shown?
3. **arithmetic** — Are the totals mathematically consistent?
4. **completeness** — Are all visible fields captured?
5. **category** — Is the category appropriate?

Score each criterion as pass/fail with a brief reason.
Give an overall_score from 1-10 (7+ = passed).
"""
