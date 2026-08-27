import sys
from pathlib import Path

# Add project root to Python path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from pipelines.inference_pipeline import InferencePipeline


def main():
    print("Initializing Inference Pipeline (Loading Model and Redis...)")
    pipeline = InferencePipeline()
    print("Initialization Complete!\n")

    # --- 1. Normal Transaction ---
    normal_data = {
        "TransactionAmt": 15.50,
        "TransactionDT": 86400,  # 1 day in
        "card1": "1000",
        "card2": "111",
        "addr2": "87.0",
        "P_emaildomain": "gmail.com",
        "DeviceType": "desktop",
    }

    print("--------------------------------------------------")
    print("[NORMAL] RUNNING NORMAL TRANSACTION")
    print(f"Input: ${normal_data['TransactionAmt']} on desktop")

    result_normal = pipeline.predict(normal_data)

    print("\nOUTPUT:")
    print(f"Risk Score:  {result_normal['risk_score']}/100")
    print(f"Risk Level:  {result_normal['risk_level']}")
    print(f"Latency:     {result_normal['latency_ms']} ms")
    print("--------------------------------------------------\n")

    # --- 2. Fraudulent Transaction ---
    fraud_data = {
        "TransactionAmt": 9500.00,
        "TransactionDT": 3600,  # Middle of the night (hour 1)
        "card1": "9999",  # Unseen card
        "card2": "999",
        "addr2": None,  # Missing address flag will trigger
        "P_emaildomain": "anonymous.com",
        "DeviceType": "mobile",
    }

    print("--------------------------------------------------")
    print("[SUSPICIOUS] RUNNING SUSPICIOUS TRANSACTION")
    print(f"Input: ${fraud_data['TransactionAmt']} in middle of night on unseen card")

    result_fraud = pipeline.predict(fraud_data)

    print("\nOUTPUT:")
    print(f"Risk Score:  {result_fraud['risk_score']}/100")
    print(f"Risk Level:  {result_fraud['risk_level']}")
    print(f"Latency:     {result_fraud['latency_ms']} ms")
    print("--------------------------------------------------\n")


if __name__ == "__main__":
    main()
