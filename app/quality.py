"""Publication gates for measured simulation targets and unresolved visual defects."""

import math


def finite_metric(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    return isinstance(value, list) and bool(value) and all(finite_metric(item) for item in value)


def require_validation(plan, validation, output):
    targets = plan.get('validation_targets') or []
    if not targets:
        raise ValueError('The plan needs at least one measurable validation target.')
    results = validation.get('results') or []
    metrics = output['metrics']
    problems = []
    for target in targets:
        ident, metric = target['id'], target['metric']
        matches = [result for result in results if result.get('id') == ident]
        if len(matches) != 1 or matches[0]['status'] != 'pass':
            problems.append(f'{ident}: the required simulation target must have exactly one passing result')
        value = metrics.get(metric)
        if not finite_metric(value):
            problems.append(f'{ident}: {metric} must have a finite measured value')
        expected = target.get('expected')
        if isinstance(expected, str):
            try:
                expected = float(expected)
            except ValueError:
                expected = None
        if isinstance(expected, (int, float)) and not isinstance(expected, bool) and finite_metric(value) and isinstance(value, (int, float)):
            if not math.isfinite(expected):
                problems.append(f'{ident}: expected value must be finite')
                continue
            try:
                tolerance = float(target.get('tolerance', 1e-6))
            except (ValueError, TypeError):
                tolerance = None  # A qualitative tolerance still requires the Validator's passing result.
            if tolerance is not None and (not math.isfinite(tolerance) or tolerance < 0 or abs(value - expected) > tolerance):
                problems.append(f'{ident}: measured {value} differs from expected {expected} beyond tolerance {tolerance}')
    if problems:
        raise ValueError('; '.join(problems))
    return validation
