from bot.client import BinanceFuturesClient

def prepare_order_params(validated_data: dict) -> dict:
    """
    Translates the validated UI/CLI input dictionary into Binance API query parameters.
    """
    order_type = validated_data["type"]
    
    # Handle Algo (Conditional) orders
    if order_type == "STOP_MARKET":
        return {
            "algoType": "CONDITIONAL",
            "symbol": validated_data["symbol"],
            "side": validated_data["side"],
            "type": "STOP_MARKET",
            "quantity": validated_data["quantity"],
            "triggerPrice": validated_data["stopPrice"],
            "workingType": "CONTRACT_PRICE"
        }
    
    # Handle Standard orders (LIMIT, MARKET)
    params = {
        "symbol": validated_data["symbol"],
        "side": validated_data["side"],
        "type": order_type,
        "quantity": validated_data["quantity"],
        "newOrderRespType": "RESULT"  # Request full response details
    }
    
    if order_type == "LIMIT":
        params["price"] = validated_data["price"]
        params["timeInForce"] = "GTC"  # Good Till Cancel
        
    return params

def place_order(client: BinanceFuturesClient, validated_data: dict) -> dict:
    """
    Places an order on Binance Futures Testnet and returns the raw API response dict.
    - Standard orders (LIMIT, MARKET) use POST /fapi/v1/order and are queried via GET.
    - Algo orders (STOP_MARKET) use POST /fapi/v1/algoOrder and return the info directly.
    """
    params = prepare_order_params(validated_data)
    order_type = validated_data["type"]
    
    if order_type == "STOP_MARKET":
        # Route conditional orders to the new dedicated Algo API
        response = client.send_signed_request(
            method="POST",
            path="/fapi/v1/algoOrder",
            params=params
        )
        return response
    
    # Standard order flow
    response = client.send_signed_request(
        method="POST",
        path="/fapi/v1/order",
        params=params
    )
    
    order_id = response.get("orderId")
    symbol = response.get("symbol")
    
    if order_id and symbol:
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                client.logger.debug(
                    f"Querying placed order details for {symbol} ID {order_id} (Attempt {attempt+1}/{max_retries})...."
                )
                query_response = client.send_signed_request(
                    method="GET",
                    path="/fapi/v1/order",
                    params={"symbol": symbol, "orderId": order_id}
                )
                return query_response
            except Exception as e:
                # If it's the "Order does not exist" error, wait and retry
                if "Order does not exist" in str(e) and attempt < max_retries - 1:
                    time.sleep(0.5)
                    continue
                client.logger.warning(
                    f"Failed to query order details on attempt {attempt+1}: {e}."
                )
                if attempt == max_retries - 1:
                    client.logger.warning("Falling back to initial response.")
    
    return response

def format_order_summary(response: dict) -> str:
    """
    Formats the Binance API response into a clean, human-readable summary block.
    Works for both standard orders and algo (conditional) orders.
    """
    # Check if it's an algo order
    is_algo = "algoId" in response
    
    # Resolve keys based on order category
    order_id = response.get("algoId") if is_algo else response.get("orderId")
    symbol = response.get("symbol")
    side = response.get("side")
    order_type = response.get("orderType") if is_algo else response.get("type")
    status = response.get("algoStatus") if is_algo else response.get("status")
    
    # Quantities
    orig_qty = response.get("quantity") if is_algo else response.get("origQty")
    executed_qty = "0.00" if is_algo else response.get("executedQty", "0")
    
    # Prices
    price = response.get("price")
    avg_price = response.get("avgPrice")
    
    if is_algo:
        avg_price = "N/A (Pending Trigger)"
    else:
        # If avgPrice is missing or '0.00000', try calculating from cumulative quote value
        if not avg_price or float(avg_price) == 0:
            cum_quote = float(response.get("cumQuote", 0))
            exec_qty_val = float(executed_qty)
            if exec_qty_val > 0:
                avg_price = f"{cum_quote / exec_qty_val:.5f}"
            else:
                avg_price = "N/A (Not Filled)"
        else:
            try:
                avg_price = f"{float(avg_price):.5f}".rstrip('0').rstrip('.')
            except ValueError:
                pass
            
    stop_price = response.get("triggerPrice") if is_algo else response.get("stopPrice")
    
    summary_lines = [
        "========================================",
        "          ORDER RESPONSE DETAILS        ",
        "========================================",
        f"Symbol:         {symbol}",
        f"Side:           {side}",
        f"Type:           {order_type}",
        f"Order ID:       {order_id}",
        f"Status:         {status}",
        f"Original Qty:   {orig_qty}",
        f"Executed Qty:   {executed_qty}",
    ]
    
    if order_type == "LIMIT" and price:
        summary_lines.append(f"Limit Price:    {price}")
    elif order_type == "STOP_MARKET" and stop_price:
        summary_lines.append(f"Stop Price:     {stop_price}")
        
    summary_lines.append(f"Avg Price:      {avg_price}")
    summary_lines.append("========================================")
    
    return "\n".join(summary_lines)
