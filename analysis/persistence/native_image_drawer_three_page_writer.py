"""Offline namespace clone of the frozen fast-tap three-page writer.

Native calls, complete executable stage bodies, guards and outer sessions remain
exact. Only identifiers, paths and three rollback descriptions are changed.
"""


def names(text):
    return (text.replace('\r\n', '\n').replace('native-github-tap-fast', 'native-image-drawer')
            .replace('native_github_tap_fast', 'native_image_drawer')
            .replace('ngtfi_', 'nidi_').replace('ngtf_', 'nid_'))


DESCRIPTION_REPLACEMENTS = (
    ('Install requires all three exact tap-v1 sector baselines',
     'Install requires all three exact fast-tap sector baselines'),
    ('Restore requires all three exact tap-v1 or all three exact github-tap-fast sector baselines',
     'Restore requires all three exact fast-tap or all three exact image-drawer sector baselines'),
    ('Restore v1 main references before returning the auxiliary slot to v1 tap.',
     'Restore fast-tap main references before returning the auxiliary slot to fast tap.'),
)


def writer(old):
    text = names(old)
    for before, after in DESCRIPTION_REPLACEMENTS:
        assert text.count(before) == 1, 'Frozen writer description anchor changed'
        text = text.replace(before, after)
    return text


def stages(old):
    # Preserve the foreach preamble before proc, not merely the procedures.
    assert old.count('foreach ngtfi_name ') == 1
    assert old.count('proc ngtfi_stage_inputs ') == 1
    return names(old[old.index('foreach ngtfi_name '):])


def outer(old):
    return names(old)
