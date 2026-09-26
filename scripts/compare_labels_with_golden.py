import csv
import json
from collections import defaultdict

GOLDEN = 'data/golden/golden_main.csv'
LABELS_DIR = 'data/labels'

# Parse golden CSV into a dict: {docId: {field: [values]}}

def load_golden(path=GOLDEN):
    data = defaultdict(lambda: defaultdict(list))
    with open(path, newline='') as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            # Ensure row has at least 3 columns
            if len(row) < 3:
                continue
            doc = row[0].strip()
            field = row[1].strip()
            value = row[2].strip()
            if doc == '':
                # some lines continue previous doc; find last seen doc
                # skip for now
                continue
            data[doc][field].append(value)
    return data


def load_label_json(path):
    with open(path) as f:
        return json.load(f)


def compare_one(golden, label_json, docid):
    g = golden.get(docid)
    if not g:
        return {'error': 'docid not in golden'}
    results = {}
    # compare product_name
    prod_g = g.get('제품명', [])
    prod_l = [label_json.get('product_name', {}).get('value')] if label_json.get('product_name') else []
    results['product_name'] = {
        'golden': prod_g,
        'label': prod_l,
        'match': any(x in prod_l for x in prod_g if x)
    }
    # compare signal_word
    sig_g = g.get('신호어', [])
    sig_l = [label_json.get('signal_word', {}).get('value')] if label_json.get('signal_word') else []
    results['signal_word'] = {
        'golden': sig_g,
        'label': sig_l,
        'match': any(x == sig_l[0] for x in sig_g) if sig_l else False
    }
    # compare hazard statements codes
    h_g = [v for v in g.get('유해위험문구', [])]
    h_l = [h.get('code') for h in label_json.get('hazard_statements', [])]
    results['hazard_codes'] = {
        'golden': h_g,
        'label': h_l,
        'match': set(h_g) == set(h_l)
    }
    # compare ingredients count
    ing_g = g.get('성분', [])
    ing_l = label_json.get('ingredients', [])
    results['ingredients_count'] = {
        'golden': len(ing_g),
        'label': len(ing_l),
        'match': len(ing_g) == len(ing_l)
    }
    return results


if __name__ == '__main__':
    import argparse
    import glob
    parser = argparse.ArgumentParser()
    parser.add_argument('--sample', type=int, default=5)
    parser.add_argument('--docs', nargs='*', help='list of docids to compare')
    args = parser.parse_args()

    golden = load_golden()
    label_files = glob.glob(LABELS_DIR + '/*.json')

    docs = args.docs
    if not docs:
        # pick first N from label filenames
        docs = [lb.split('/')[-1].replace('.json', '') for lb in label_files][:args.sample]

    for doc in docs:
        path = f'{LABELS_DIR}/{doc}.json'
        try:
            lj = load_label_json(path)
        except FileNotFoundError:
            print(doc, 'label file not found')
            continue
        res = compare_one(golden, lj, doc)
        print('---', doc)
        print(json.dumps(res, ensure_ascii=False, indent=2))
