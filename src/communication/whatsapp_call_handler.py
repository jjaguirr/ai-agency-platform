
# WhatsApp Call Handler for EA
async def handle_incoming_call(call_data):
    """Handle incoming WhatsApp call"""
    from_number = call_data.get('from')
    call_id = call_data.get('call_id')
    call_status = call_data.get('status')
    
    if call_status == 'call_answered':
        # Call answered - start EA conversation
        await start_voice_conversation(from_number, call_id)
    elif call_status == 'call_ended':
        # Call ended - send follow-up message
        await send_call_summary(from_number, call_id)

async def start_voice_conversation(phone_number, call_id):
    """Start voice conversation with EA"""
    # Initialize EA
    ea = ExecutiveAssistant(customer_id=f"customer_{phone_number}")
    
    # Generate welcome message
    welcome = await ea.handle_customer_interaction(
        "Starting voice call conversation", 
        ConversationChannel.WHATSAPP
    )
    
    # Convert to voice and play
    voice_data = await generate_voice_response(welcome)
    await play_voice_in_call(call_id, voice_data)

async def send_call_summary(phone_number, call_id):
    """Send summary after call ends"""
    summary = f"📞 Call Summary\n\nThanks for calling! Here's what we discussed:\n\n[AI will generate summary based on call transcript]\n\nNeed anything else? Just message me!"
    
    await send_whatsapp_message(phone_number, summary)
