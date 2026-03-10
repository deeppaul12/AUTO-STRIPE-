from flask import Flask, request, jsonify
import stripe
import threading

app = Flask(__name__)

# ==================== CONFIGURATION ====================
# YAHAN APNI LIVE KEY DAALO
# WARNING: Ye real paise kat degi agar card valid hogi. 
# Authorizations mostly refund ho jate hain, but careful raho.

API_KEYS_LIST = [
    ""  # Aapki Live Key
]

# Global Variables
current_key_index = 0
key_lock = threading.Lock()

def get_active_key():
    global current_key_index
    with key_lock:
        if not API_KEYS_LIST:
            return None
        key = API_KEYS_LIST[current_key_index]
        stripe.api_key = key
        return key

def switch_to_next_key():
    global current_key_index
    with key_lock:
        if len(API_KEYS_LIST) > 1:
            current_key_index = (current_key_index + 1) % len(API_KEYS_LIST)
            print(f"[KEY SWITCH] Switching to Key Index: {current_key_index}")

# ==================== AUTO STRIPE LOGIC (LIVE MODE) ====================
def process_payment(cc, site):
    try:
        key = get_active_key()
        if not key:
            return {"status": "error", "response": "No API Keys Configured"}

        parts = cc.split('|')
        if len(parts) < 4:
            return {"status": "error", "response": "Invalid Format"}
        
        cc_num, mm, yy, cvc = parts[0], parts[1], parts[2], parts[3]
        
        # Year Adjustment
        if len(yy) == 2:
            yy = "20" + yy

        # STEP 1: Create Token
        try:
            token = stripe.Token.create(
                card={
                    "number": cc_num,
                    "exp_month": mm,
                    "exp_year": yy,
                    "cvc": cvc,
                }
            )
        except stripe.error.InvalidRequestError as e:
            return {"status": "declined", "response": "Invalid Card Info"}
        except stripe.error.AuthenticationError:
            switch_to_next_key()
            return process_payment(cc, site)

        # STEP 2: Payment Intent (AUTHORIZATION)
        try:
            # YAHAAN CHANGE HUA HAI: Amount 50 Cents ($0.50)
            # Ye minimum amount hai Live Accounts ke liye zyadatar cases mein
            # Agar aapko $1 hi karna hai aur error aaye to isko 100 kar do
            
            intent = stripe.PaymentIntent.create(
                amount=50,  # 50 Cents = $0.50 (Safe for Live)
                currency='usd',
                payment_method_types=['card'],
                payment_method_data={
                    'type': 'card',
                    'card': {'token': token.id}
                },
                confirm=True,
                description=f"Auth for {site}",
                metadata={'site': site}
                # Note: Capture_method='manual' se paise hold hote hain, 
                # automatic se charge ho jate hain. Default automatic hai.
            )

            if intent.status == 'succeeded':
                # LIVE CARD - CHARGED
                return {"status": "approved", "response": "Charged $0.50 (Live)"}
            elif intent.status == 'requires_action':
                # 3D Secure
                return {"status": "approved", "response": "3D Secure Required"}
            else:
                return {"status": "declined", "response": f"Status: {intent.status}"}

        except stripe.error.CardError as e:
            err_msg = e.error.message
            code = e.error.code
            
            # Live accounts mein "insufficient funds" = Card Valid hai
            if "insufficient funds" in err_msg.lower():
                return {"status": "approved", "response": "Live Card (Insufficient Funds)"}
            if "card_declined" in code:
                 return {"status": "approved", "response": f"Live (Declined by Bank: {err_msg})"}

            return {"status": "declined", "response": err_msg}

        except stripe.error.InvalidRequestError as e:
            # Agar Amount 1 se kam wala error aaye
            error_body = str(e)
            if "amount must be at least" in error_body.lower():
                # Retry with $1 (100 cents) if 50 fails
                print("[INFO] Retrying with $1 amount...")
                intent = stripe.PaymentIntent.create(
                    amount=100, currency='usd',
                    payment_method_types=['card'],
                    payment_method_data={'type': 'card', 'card': {'token': token.id}},
                    confirm=True
                )
                if intent.status == 'succeeded':
                    return {"status": "approved", "response": "Charged $1.00 (Live)"}
            
            return {"status": "error", "response": f"Stripe Error: {e}"}

        except stripe.error.RateLimitError:
            switch_to_next_key()
            return {"status": "error", "response": "Rate Limit - Retrying..."}
            
    except Exception as e:
        return {"status": "error", "response": f"Global Error: {str(e)}"}

# ==================== ENDPOINT ====================
@app.route('/check', methods=['GET'])
def check_route():
    gateway = request.args.get('gateway')
    key = request.args.get('key')
    site = request.args.get('site')
    cc = request.args.get('cc')

    if key != "Beast":
        return jsonify({"status": "error", "response": "Wrong Key"})

    print(f"[LIVE CHECK] Card: {cc[:6]}... | Site: {site}")

    if gateway == "autostripe":
        res = process_payment(cc, site)
    else:
        res = {"status": "error", "response": "Unknown Gateway"}

    return jsonify(res)

if __name__ == '__main__':
    print("====================================")
    print("   LIVE STRIPE SERVER STARTED")
    print("   WARNING: USING LIVE SK KEYS")
    print("====================================")
    app.run(host='0.0.0.0', port=10100, threaded=True)
