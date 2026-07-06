# web-Brickrat

FastAPI product studio for turning furniture images into TripoSR OBJ/GLB models
and saving product metadata and asset links to Supabase.

## Run

```powershell
cd C:\Git\TripoSR\web-Brickrat
pip install -r requirements.txt
Copy-Item .env.example .env
# Fill in the Supabase values in .env
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000`. Before saving a product, run `supabase.sql` in
the Supabase SQL editor and create a public Storage bucket named `products`.

The application uses the TripoSR source in the parent `C:\Git\TripoSR`
directory. Model weights load on the first conversion request.
