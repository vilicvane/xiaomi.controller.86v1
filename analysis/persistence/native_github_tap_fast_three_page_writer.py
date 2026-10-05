"""Offline-only namespace clone of the exact frozen v1 tap three-page writer.

All native calls, allowlisted stages, protection and public flow stay unchanged.
Only new names/paths, two baseline-error descriptions and one rollback comment differ.
"""


def names(text):
    return (text.replace('\r\n', '\n').replace('native-github-tap', 'native-github-tap-fast')
            .replace('native_github_tap', 'native_github_tap_fast')
            .replace('ngti_', 'ngtfi_').replace('ngt_', 'ngtf_'))


DESCRIPTION_REPLACEMENTS = (
    ('Install requires all three exact card-v1 sector baselines',
     'Install requires all three exact tap-v1 sector baselines'),
    ('Restore requires all three exact card-v1 or all three exact github-tap sector baselines',
     'Restore requires all three exact tap-v1 or all three exact github-tap-fast sector baselines'),
    ('Remove all main references before returning the auxiliary slot to stock.',
     'Restore v1 main references before returning the auxiliary slot to v1 tap.'),
)


def writer(old):
    text = names(old)
    for before, after in DESCRIPTION_REPLACEMENTS:
        assert text.count(before) == 1, 'Frozen writer description anchor changed'
        text = text.replace(before, after)
    return text


def stages(old):
    # The frozen array preamble is regenerated from independently checked new
    # full-page fixtures; the entire executable stage body stays exact.
    assert old.count('foreach ngti_name ') == 1
    assert old.count('proc ngti_stage_inputs ') == 1
    return names(old[old.index('foreach ngti_name '):])


def outer(old):
    return names(old)
