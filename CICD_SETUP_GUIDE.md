# GitHub Actions CI/CD Setup Guide

## ✅ What's Been Set Up

### Backend CI (`.github/workflows/backend-ci.yml`)
- **Lint Job**: Runs flake8 to check code quality
- **Test Job**: Runs pytest with PostgreSQL database
- **Triggers**: On every commit to any branch when backend files change

### Frontend CI (`.github/workflows/frontend-ci.yml`)
- **Lint Job**: Runs ESLint and TypeScript type checking
- **Test Job**: Runs Jest tests (if configured)
- **Build Job**: Builds the Next.js application
- **Triggers**: On every commit to any branch when frontend files change

---

## 🔑 Adding GitHub Secrets

### Step 1: Go to Repository Settings
1. Open your GitHub repository: https://github.com/muhammadMubeen247/The-Learning-SAMpai
2. Click on **Settings** (top navigation bar)
3. In the left sidebar, click **Secrets and variables** → **Actions**

### Step 2: Add OPENAI_API_KEY Secret
1. Click the green **"New repository secret"** button
2. Fill in the form:
   - **Name**: `OPENAI_API_KEY`
   - **Secret**: Paste your OpenAI API key (starts with `sk-`)
3. Click **"Add secret"**

### Step 3: Verify the Secret
- You should see `OPENAI_API_KEY` listed under "Repository secrets"
- The value will be hidden (shown as `***`)
- This secret will be available to all workflows

---

## 🧪 Testing Requirements

### Backend Tests
Your backend already has test files in `backend/app/tests/`:
- `test_document_processor.py`
- `test_file_pipeline.py`
- `test_langchain_phase1.py`
- `test_langchain_phase2.py`
- `test_langchain_phase3.py`
- `test_topic_extractor.py`
- `test_vector_store.py`

**Testing dependencies added to `requirements.txt`:**
- `pytest==8.0.0`
- `pytest-asyncio==0.23.5`
- `httpx==0.28.1` (already present)

### Frontend Tests
Your frontend doesn't have a test script configured yet. The workflow will:
- Skip tests gracefully if no test script exists
- Run tests automatically once you add them

**To add frontend tests later:**
1. Install testing libraries: `pnpm add -D jest @testing-library/react @testing-library/jest-dom`
2. Add test script to `package.json`:
   ```json
   "scripts": {
     "test": "jest"
   }
   ```

---

## 🚀 How to Use

### Triggering Workflows

**Automatically:**
```bash
# Make any change to backend or frontend
git add .
git commit -m "your commit message"
git push
```

The workflows will automatically run when you push to any branch.

### Viewing Workflow Results

1. Go to your repository on GitHub
2. Click the **Actions** tab
3. You'll see all workflow runs listed
4. Click on any run to see detailed logs
5. Each job (Lint, Test, Build) can be expanded to see step-by-step output

### Workflow Status

**Success**: ✅ Green checkmark - All jobs passed
**Failure**: ❌ Red X - One or more jobs failed (click to see which)
**Running**: 🟡 Yellow circle - Workflow is currently running

---

## 🧪 Testing Locally Before Pushing

### Backend
```bash
cd backend

# Install dependencies (including test dependencies)
pip install -r requirements.txt

# Run tests
pytest app/tests/ -v

# Run linting
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
```

### Frontend
```bash
cd frontend

# Install dependencies
pnpm install

# Run linting
pnpm lint

# Check types
npx tsc --noEmit

# Build
pnpm build
```

---

## 🐛 Troubleshooting

### "OPENAI_API_KEY not found"
- Ensure you added the secret correctly in GitHub Settings
- Secret name must be exactly `OPENAI_API_KEY` (case-sensitive)
- Push another commit to re-trigger the workflow

### "Tests Failed"
- Check the workflow logs to see which test failed
- Run the same tests locally to debug
- Make sure all required environment variables are set

### "Workflow Not Triggering"
- Ensure you're modifying files in `backend/` or `frontend/` directories
- Check that `.github/workflows/` files are committed to your repository
- Verify you pushed to GitHub (not just committed locally)

### "PostgreSQL Connection Failed"
- The workflow automatically starts a PostgreSQL service
- If tests fail, check the logs for database connection errors
- Ensure your tests are using the `DATABASE_URL` environment variable

---

## 📊 What Gets Tested

### Backend CI Pipeline
1. **Code Quality** (Lint Job)
   - Checks for syntax errors
   - Checks code complexity
   - Validates Python best practices

2. **Functionality** (Test Job)
   - Runs all pytest tests
   - Uses a real PostgreSQL database
   - Tests document processing, RAG, vector store, etc.

### Frontend CI Pipeline
1. **Code Quality** (Lint Job)
   - ESLint checks
   - TypeScript type checking

2. **Build Validation** (Build Job)
   - Ensures Next.js app builds successfully
   - Catches build-time errors

---

## ✨ Next Steps

1. ✅ Add `OPENAI_API_KEY` secret to GitHub
2. ✅ Push a commit to trigger the workflows
3. ✅ Check the Actions tab to see results
4. ⬜ (Optional) Add frontend tests
5. ⬜ (Optional) Add more backend tests as needed

---

## 📝 Notes

- Workflows only run on branches where the workflow files exist
- Each workflow run uses fresh Ubuntu runners
- Dependencies are cached to speed up subsequent runs
- Failed workflows will show up as failed checks on pull requests
- You can re-run failed workflows from the Actions tab

**That's it! Your CI/CD is ready to use.** 🎉
