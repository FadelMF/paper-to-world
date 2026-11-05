"""Small, untrained encoder-decoder Transformer following §§3.1–3.5.

One layer, d_model=4, two heads and d_ff=8 keep every operation inspectable.
Fixed deterministic weights demonstrate architecture; they are not a translation model.
"""

import json
import math

DEFAULTS = {
    'source': 0,
    'position': 1,
    'memory': 1,
    'prefix': 3,
    'causal': 1,
    'stage': 0,
    'head': 0,
    'training_step': 4000,
    'input_gain': 100,
    'position_gain': 100,
    'score_gain': 100,
    'memory_gain': 100,
}
EMBEDDINGS = [[math.sin((i + 1) * (j + 1)) * 0.6 for j in range(4)] for i in range(6)]


def weights(rows, cols, seed):
    return [[math.sin((r + 1) * (c + 1) + seed) * 0.35 for c in range(cols)] for r in range(rows)]


def matmul(a, b):
    return [[sum(x * b[k][j] for k, x in enumerate(row)) for j in range(len(b[0]))] for row in a]


def softmax(row):
    peak = max(row)
    exps = [math.exp(x - peak) for x in row]
    return [x / sum(exps) for x in exps]


def norm_add(a, b):
    result = []
    for ra, rb in zip(a, b, strict=True):
        row = [x + y for x, y in zip(ra, rb, strict=True)]
        mean = sum(row) / 4
        denom = math.sqrt(sum((x - mean) ** 2 for x in row) / 4 + 1e-5)
        result.append([(x - mean) / denom for x in row])
    return result


def embed(tokens, positional):
    return [
        [
            EMBEDDINGS[t][d] * 2 + positional * (math.sin(i / 10000 ** (2 * (d // 2) / 4)) if d % 2 == 0 else math.cos(i / 10000 ** (2 * (d // 2) / 4)))
            for d in range(4)
        ]
        for i, t in enumerate(tokens)
    ]


def multihead(query, memory, seed, causal=False, score_gain=100):
    q, k, v = [matmul(x, weights(4, 4, seed + offset)) for x, offset in [(query, 0), (memory, 1), (memory, 2)]]
    heads, attention = [], []
    for h in range(2):
        rows, values = [], []
        for i, row in enumerate(q):
            scores = [
                sum(row[h * 2 + d] * key[h * 2 + d] for d in range(2)) / math.sqrt(2) * score_gain / 100 if not causal or j <= i else -1e9
                for j, key in enumerate(k)
            ]
            a = softmax(scores)
            rows.append(a)
            values.append([sum(a[j] * v[j][h * 2 + d] for j in range(len(v))) for d in range(2)])
        heads.append(values)
        attention.append(rows)
    concat = [heads[0][i] + heads[1][i] for i in range(len(query))]
    return matmul(concat, weights(4, 4, seed + 3)), attention, heads, concat


def feedforward(x):
    hidden = matmul(x, weights(4, 8, 18))
    return matmul([[max(0, v + 0.1) for v in row] for row in hidden], weights(8, 4, 19))


def forward(params):
    p = {**DEFAULTS, **params}
    source_ids = [1, 2 if p['source'] == 0 else 4, 3]
    embedded = embed(source_ids, p['position'] * p['position_gain'] / 100)
    embedded = [[v * p['input_gain'] / 100 for v in row] for row in embedded]
    enc_attn, enc_weights, heads, concat = multihead(embedded, embedded, 1, score_gain=p['score_gain'])
    enc_norm = norm_add(embedded, enc_attn)
    enc_ff = feedforward(enc_norm)
    encoder = norm_add(enc_norm, enc_ff)
    prefix, generated = [0], []
    for _ in range(int(p['prefix'])):
        target = embed(prefix, p['position'] * p['position_gain'] / 100)
        dec_self, self_weights, _, _ = multihead(target, target, 7, bool(p['causal']), p['score_gain'])
        dec_norm = norm_add(target, dec_self)
        memory = [[v * p['memory'] * p['memory_gain'] / 100 for v in row] for row in encoder]
        cross, cross_weights, _, _ = multihead(dec_norm, memory, 12, score_gain=p['score_gain'])
        cross_norm = norm_add(dec_norm, cross)
        dec_ff = feedforward(cross_norm)
        decoder = norm_add(cross_norm, dec_ff)
        logits = matmul([decoder[-1]], weights(4, 6, 23))[0]
        probabilities = softmax(logits)
        predicted = max(range(6), key=lambda i: probabilities[i])
        generated.append(predicted)
        if len(generated) < int(p['prefix']):
            prefix.append(predicted)
    future_mass = sum(self_weights[h][i][j] for h in range(2) for i in range(len(prefix)) for j in range(i + 1, len(prefix)))
    return {
        **p,
        'source_ids': source_ids,
        'prefix_ids': prefix,
        'generated': generated,
        'embedded': embedded,
        'encoder_attention': enc_attn,
        'encoder_queries': matmul(embedded, weights(4, 4, 1)),
        'encoder_keys': matmul(embedded, weights(4, 4, 2)),
        'encoder_values': matmul(embedded, weights(4, 4, 3)),
        'encoder_norm': enc_norm,
        'encoder_ff': enc_ff,
        'encoder': encoder,
        'target_embedded': target,
        'decoder_self': dec_self,
        'decoder_norm': dec_norm,
        'cross': cross,
        'decoder_ff': dec_ff,
        'decoder': decoder,
        'enc_weights': enc_weights,
        'self_weights': self_weights,
        'cross_weights': cross_weights,
        'head_outputs': heads,
        'concat': concat,
        'probabilities': probabilities,
        'learning_rate': 512**-0.5 * min(p['training_step'] ** -0.5, p['training_step'] * 4000**-1.5),
        'predicted': predicted,
        'future_mass': future_mass,
        'probability_sum': sum(probabilities),
        'memory_energy': sum(abs(v) for row in cross for v in row),
        'position_energy': sum(abs(v) for row in embedded for v in row),
    }


def run(params, steps):
    return {**forward(params), 'time': steps * 0.1, 'phase': (steps // 8) % 12}


if __name__ == '__main__':
    s = run({}, 0)
    print(
        json.dumps(
            {
                'metrics': {'probability_sum': s['probability_sum'], 'future_mass': s['future_mass'], 'generated_tokens': len(s['generated'])},
                'notes': 'Untrained one-layer encoder-decoder, d_model=4, h=2, d_ff=8. Architecture/equation checks, not BLEU reproduction.',
            }
        )
    )
