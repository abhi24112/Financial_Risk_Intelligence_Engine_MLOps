# This file will have all the reusable queries


class Queries:

    GET_ALL_TRANSACTIONS = """
        select *
        from train_transaction
    """

    GET_ALL_IDENTITY = """
        select *
        from train_identity
    """
    FRAUD_TRANSACTIONS = """
        SELECT *
        FROM train_transaction
        WHERE isFraud = 1
    """

    NON_FRAUD_TRANSACTIONS = """
        SELECT *
        FROM train_transaction
        WHERE isFraud = 0
    """
