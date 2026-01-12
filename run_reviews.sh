#!/bin/bash
# Run external model reviews using curl

set -e

# Read review files
REVIEW_PACKAGE=$(cat REVIEW_PACKAGE.md)
CONTAINMENT_PROPOSAL=$(cat CONTAINMENT_PROPOSAL.md)

PROMPT="# Review Request

Please review the following multi-repo support and containment strategy for the workflow-orchestrator project.

$REVIEW_PACKAGE

---

# Full Technical Specification

$CONTAINMENT_PROPOSAL

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

Please be specific, cite examples, and identify potential issues we haven't considered."

# Create output directory
mkdir -p .orchestrator

# OpenAI GPT-4 Review
echo "🔍 Reviewing with GPT-4..."
OPENAI_RESPONSE=$(curl -s https://api.openai.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "model": "gpt-4-turbo-preview",
    "messages": [
      {"role": "system", "content": "You are an expert software architect reviewing a codebase refactoring proposal."},
      {"role": "user", "content": '"$(echo "$PROMPT" | jq -Rs .)"'}
    ],
    "temperature": 0.7,
    "max_tokens": 4000
  }')

echo "$OPENAI_RESPONSE" | jq -r '.choices[0].message.content' > .orchestrator/review_gpt4.md
echo "✅ GPT-4 review saved to .orchestrator/review_gpt4.md"

# Gemini Review
echo "🔍 Reviewing with Gemini..."
GEMINI_RESPONSE=$(curl -s "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=$GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [{
      "parts": [{"text": '"$(echo "$PROMPT" | jq -Rs .)"'}]
    }]
  }')

echo "$GEMINI_RESPONSE" | jq -r '.candidates[0].content.parts[0].text' > .orchestrator/review_gemini.md
echo "✅ Gemini review saved to .orchestrator/review_gemini.md"

# OpenRouter (Claude Opus)
echo "🔍 Reviewing with Claude Opus via OpenRouter..."
CLAUDE_RESPONSE=$(curl -s https://openrouter.ai/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -d '{
    "model": "anthropic/claude-opus",
    "messages": [
      {"role": "system", "content": "You are an expert software architect reviewing a codebase refactoring proposal."},
      {"role": "user", "content": '"$(echo "$PROMPT" | jq -Rs .)"'}
    ],
    "temperature": 0.7,
    "max_tokens": 4000
  }')

echo "$CLAUDE_RESPONSE" | jq -r '.choices[0].message.content' > .orchestrator/review_claude_opus.md
echo "✅ Claude Opus review saved to .orchestrator/review_claude_opus.md"

# OpenRouter (DeepSeek)
echo "🔍 Reviewing with DeepSeek via OpenRouter..."
DEEPSEEK_RESPONSE=$(curl -s https://openrouter.ai/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -d '{
    "model": "deepseek/deepseek-chat",
    "messages": [
      {"role": "system", "content": "You are an expert software architect reviewing a codebase refactoring proposal."},
      {"role": "user", "content": '"$(echo "$PROMPT" | jq -Rs .)"'}
    ],
    "temperature": 0.7,
    "max_tokens": 4000
  }')

echo "$DEEPSEEK_RESPONSE" | jq -r '.choices[0].message.content' > .orchestrator/review_deepseek.md
echo "✅ DeepSeek review saved to .orchestrator/review_deepseek.md"

# Create combined markdown file
echo "📝 Creating combined review document..."
cat > EXTERNAL_REVIEWS.md << 'EOF'
# External Model Reviews

Reviews of the multi-repo support and containment strategy.

---

## GPT-4 (OpenAI)

EOF

cat .orchestrator/review_gpt4.md >> EXTERNAL_REVIEWS.md

cat >> EXTERNAL_REVIEWS.md << 'EOF'

---

## Gemini 2.0 Flash (Google)

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

echo "✅ Combined reviews saved to EXTERNAL_REVIEWS.md"
echo ""
echo "================================================================================  "
echo "REVIEW SUMMARY"
echo "================================================================================"
echo "✅ 4 model reviews completed"
echo "📄 Combined reviews: EXTERNAL_REVIEWS.md"
echo "📁 Individual reviews: .orchestrator/review_*.md"
