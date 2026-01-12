#!/bin/bash
# Run external model reviews using curl

set -e

# Create prompt file
cat > /tmp/review_prompt.txt << 'PROMPT_END'
# Review Request

Please review the following multi-repo support and containment strategy for the workflow-orchestrator project.

PROMPT_END

cat REVIEW_PACKAGE.md >> /tmp/review_prompt.txt

cat >> /tmp/review_prompt.txt << 'PROMPT_END'

---

PROMPT_END

cat CONTAINMENT_PROPOSAL.md >> /tmp/review_prompt.txt

cat >> /tmp/review_prompt.txt << 'PROMPT_END'

---

# Your Task

Please provide a detailed review addressing:

1. **Architecture Assessment**: Is the containment strategy sound? Any edge cases or risks?
2. **Migration Path**: Is the 4-phase migration plan reasonable? Better alternatives?
3. **Multi-Repo Support**: What gaps remain for seamless multi-repo usage?
4. **Web Compatibility**: Critical considerations for Claude Code Web (ephemeral sessions)?
5. **Implementation**: Feedback on PathResolver design and auto-migration approach?
6. **User Experience**: How to minimize disruption to existing users?
7. **Recommendations**: What should be prioritized? Alternative approaches?

Please be specific, cite examples, and identify potential issues we haven't considered.
PROMPT_END

# Create output directory
mkdir -p .orchestrator

# Helper function to create JSON payload
create_payload() {
    local model="$1"
    local prompt=$(cat /tmp/review_prompt.txt | jq -Rs .)

    if [[ "$model" == "gemini" ]]; then
        cat <<EOF
{
  "contents": [{
    "parts": [{"text": $prompt}]
  }]
}
EOF
    else
        cat <<EOF
{
  "model": "$model",
  "messages": [
    {"role": "system", "content": "You are an expert software architect reviewing a codebase refactoring proposal."},
    {"role": "user", "content": $prompt}
  ],
  "temperature": 0.7,
  "max_tokens": 4000
}
EOF
    fi
}

# GPT-4 Review
echo "🔍 Reviewing with GPT-4..."
create_payload "gpt-4-turbo-preview" > /tmp/payload_gpt4.json
curl -s https://api.openai.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d @/tmp/payload_gpt4.json | jq -r '.choices[0].message.content // .error.message // "Error"' > .orchestrator/review_gpt4.md
echo "✅ GPT-4 review saved"

# Gemini Review
echo "🔍 Reviewing with Gemini..."
create_payload "gemini" > /tmp/payload_gemini.json
curl -s "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=$GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d @/tmp/payload_gemini.json | jq -r '.candidates[0].content.parts[0].text // .error.message // "Error"' > .orchestrator/review_gemini.md
echo "✅ Gemini review saved"

# Claude Opus Review
echo "🔍 Reviewing with Claude Opus..."
create_payload "anthropic/claude-opus" > /tmp/payload_claude.json
curl -s https://openrouter.ai/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -d @/tmp/payload_claude.json | jq -r '.choices[0].message.content // .error.message // "Error"' > .orchestrator/review_claude_opus.md
echo "✅ Claude Opus review saved"

# DeepSeek Review
echo "🔍 Reviewing with DeepSeek..."
create_payload "deepseek/deepseek-chat" > /tmp/payload_deepseek.json
curl -s https://openrouter.ai/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -d @/tmp/payload_deepseek.json | jq -r '.choices[0].message.content // .error.message // "Error"' > .orchestrator/review_deepseek.md
echo "✅ DeepSeek review saved"

# Create combined markdown
echo "📝 Creating combined review document..."
cat > EXTERNAL_REVIEWS.md << 'EOF'
# External Model Reviews

Reviews of the multi-repo support and containment strategy for workflow-orchestrator.

Date: $(date +%Y-%m-%d)

---

## GPT-4 Turbo (OpenAI)

EOF

cat .orchestrator/review_gpt4.md >> EXTERNAL_REVIEWS.md

cat >> EXTERNAL_REVIEWS.md << 'EOF'

---

## Gemini 2.0 Flash Exp (Google)

EOF

cat .orchestrator/review_gemini.md >> EXTERNAL_REVIEWS.md

cat >> EXTERNAL_REVIEWS.md << 'EOF'

---

## Claude Opus (Anthropic via OpenRouter)

EOF

cat .orchestrator/review_claude_opus.md >> EXTERNAL_REVIEWS.md

cat >> EXTERNAL_REVIEWS.md << 'EOF'

---

## DeepSeek Chat

EOF

cat .orchestrator/review_deepseek.md >> EXTERNAL_REVIEWS.md

echo "✅ All reviews completed!"
echo ""
echo "================================================================================"
echo "REVIEW SUMMARY"
echo "================================================================================"
echo "✅ 4 model reviews completed"
echo "📄 Combined reviews: EXTERNAL_REVIEWS.md"
echo "📁 Individual reviews: .orchestrator/review_*.md"
echo ""
echo "Preview:"
head -20 EXTERNAL_REVIEWS.md
