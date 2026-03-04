from fastapi.testclient import TestClient
from app.main import app


def ingest_textbook_doc():
    client = TestClient(app)
    with open("tests/upload_test/first-chap-rudin.pdf", "rb") as filestream:
        files_payload = {
            "file": ("first-chap-rudin", filestream, "application/pdf")
        }
        
        response = client.post(
            "/upload_doc",
            files=files_payload
        )
    
    assert response.status_code == 200

if __name__ == "__main__":
    try:
        # get_trace()
        ingest_textbook_doc()
        print("Test passed!")
    except AssertionError as e:
        print(f"Test failed as expected (or unexpected): {e}")
    except Exception as e:
        print(f"An error occurred: {e}")