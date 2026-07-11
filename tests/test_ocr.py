from app.services.ocr import extract_result_payload, to_python_value


class FakeArray:
    def tolist(self) -> list[int]:
        return [1, 2, 3]


class FakePrediction:
    def json(self) -> dict[str, dict[str, list[str]]]:
        return {"res": {"rec_texts": ["Xin chào"]}}


def test_to_python_value_converts_nested_arrays() -> None:
    assert to_python_value({"box": FakeArray()}) == {"box": [1, 2, 3]}


def test_extract_result_payload_unwraps_res() -> None:
    assert extract_result_payload(FakePrediction()) == {
        "rec_texts": ["Xin chào"]
    }
