"""The generator's printed labels must equal the schema's declared labels.

CP15's extractor anchors on `FieldSpec.label` and reads the value beside it, so the schema
and the renderer disagreeing is not cosmetic -- it silently breaks extraction for that
field. It did: the schema declared `label="Urgency (Standard/Urgent)"` while the form
printed `"Urgency:"`, and the anchor matched the two-token window ['Urgency:', 'Standard']
at 0.82, absorbing the value into the label. The field then extracted the NEXT row's label
as its value, and the eval reported 0% for one field while the aggregate still passed.

Three separate diagnostics were spent finding that, so it is worth one cheap test. This is
the class of bug -- two sources of truth quietly drifting -- not the instance.
"""

from chartwright_schemas.documents import SCHEMA_REGISTRY
from chartwright_schemas.taxonomy import DocType
from chartwright_synthdata.generator import _FORM_ROWS


class TestPrintedLabelsMatchSchema:
    def test_every_printed_row_label_matches_its_field_spec(self) -> None:
        schema = SCHEMA_REGISTRY[DocType.PRIOR_AUTH_REQUEST]
        by_key = {f.key: f.label for f in schema.fields}
        mismatches = [
            f"{key}: form prints {printed!r} but schema declares {by_key[key]!r}"
            for key, printed, _ in _FORM_ROWS
            if key in by_key and printed != by_key[key]
        ]
        assert not mismatches, "generator/schema label drift:\n  " + "\n  ".join(mismatches)

    def test_every_printed_row_key_exists_in_the_schema(self) -> None:
        schema = SCHEMA_REGISTRY[DocType.PRIOR_AUTH_REQUEST]
        unknown = [key for key, _, _ in _FORM_ROWS if key not in schema.field_keys()]
        assert not unknown, f"generator renders keys absent from the schema: {unknown}"

    def test_labels_do_not_embed_their_allowed_values(self) -> None:
        """A printed form label is a label, not a hint about permitted values.

        A parenthetical that repeats a value the form also prints is what broke `urgency`.
        Genuine printed parentheses (e.g. 'Diagnosis Code (ICD-10)') are fine, because the
        form prints them too -- which is exactly what the first test above enforces.
        """
        schema = SCHEMA_REGISTRY[DocType.PRIOR_AUTH_REQUEST]
        printed = {key: label for key, label, _ in _FORM_ROWS}
        offenders = [
            f.key
            for f in schema.fields
            if f.key in printed and f.label != printed[f.key] and "(" in f.label
        ]
        assert not offenders, f"labels embed non-printed parentheticals: {offenders}"
