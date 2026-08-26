"""Check the review packet for any leaked authorial labels."""
text = open('data/labels/review_packet.md', encoding='utf-8').read()
body = text.split('---', 1)[-1]

leaked = False
for term in ['failure_class', 'ambiguous_instruction', 'ambiguity_detail',
             'ground_truth', 'rationale', 'actually wanted',
             'AGENT_INTERPRETATION_ERROR', 'AMBIGUOUS_HUMAN_INSTRUCTION',
             'DUPLICATE_OR_RETRY_EXECUTION', 'MERCHANT_OR_CART_MANIPULATION',
             'MERCHANT_PROMPT_OR_CATALOG_INJECTION',
             'SYSTEM_STATE_OR_EVIDENCE_INCONSISTENCY',
             'split:', 'dev', 'holdout']:
    if term in body:
        # 'dev' might appear in normal text - check context
        if term in ('dev', 'holdout'):
            lines = [l for l in body.split('\n') if term in l.split()]
            if lines:
                leaked = True
                print(f'POSSIBLE LEAK: "{term}" found in body')
                for l in lines[:2]:
                    print(f'  {l.strip()[:120]}')
        else:
            leaked = True
            count = body.count(term)
            print(f'LEAK: "{term}" found {count} time(s)')

if not leaked:
    print('CLEAN: No authorial labels found in review packet body.')

scenario_count = text.count('## SC-')
blank_count = text.count('________')
print(f'Scenarios: {scenario_count}')
print(f'Judgment blanks: {blank_count} (expected {scenario_count * 3})')
