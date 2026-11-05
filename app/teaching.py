"""Coverage gates between paper analysis, lesson planning and authored lessons."""


def validate_coverage(analysis, plan, lessons=None):
    topics = analysis.get('learning_topics') or []
    if not topics:
        return {'status': 'legacy', 'topics': [], 'limitations': ['This older extraction has no paper coverage map.']}
    entries = plan.get('coverage') or []
    mapped = {entry.get('topic'): entry for entry in entries}
    problems, report = [], []
    lesson_map = {lesson['id']: lesson for lesson in lessons or []}
    for topic in topics:
        entry = mapped.get(topic['id'])
        if not entry or entry.get('mode') not in ('simulated', 'explained', 'excluded'):
            problems.append(f"Missing coverage for {topic['title']}")
            continue
        if entry['mode'] == 'excluded':
            if topic.get('required', True) or not entry.get('reason'):
                problems.append(f"Required topic {topic['title']} cannot silently be excluded")
        elif not entry.get('lessons'):
            problems.append(f"{topic['title']} needs lesson IDs")
        if lessons is not None:
            for ident in entry.get('lessons') or []:
                lesson = lesson_map.get(ident)
                if lesson is None:
                    problems.append(f"{topic['title']} points to missing lesson {ident}")
                elif not lesson.get('learning'):
                    problems.append(f"{ident} needs an objective, action and observable outcome")
        report.append({**topic, **entry})
    if problems:
        raise ValueError('; '.join(problems))
    return {'status': 'mapped', 'topics': report, 'limitations': plan.get('simplifications') or []}
