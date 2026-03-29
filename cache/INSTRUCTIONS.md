# Cold Flow 3/15 — Dashboard Instructions

This dashboard lets you interactively explore the cold flow test data from 3/15/2026.
All the data is already saved locally — no internet connection is needed to run it.

---

## What you need

- A Windows or Mac computer
- An internet connection **for the one-time setup only**

---

## Step 1 — Install Python (one time only)

1. Go to **https://www.python.org/downloads** and download the latest Python 3 installer.
2. Run the installer.
   - **Windows:** Before clicking Install, check the box that says **"Add Python to PATH"** — this is important.
   - Click **Install Now** and let it finish.
3. Close the installer when done.

---

## Step 2 — Open a terminal inside this folder

**Windows:**
1. Open the `coldflow-3-15` folder in File Explorer.
2. Click the address bar at the top of the window (where it shows the folder path).
3. Type `cmd` and press **Enter**.
4. A black terminal window will open, already pointed at this folder.

**Mac:**
1. Open the `coldflow-3-15` folder in Finder.
2. Right-click (or Control-click) anywhere inside the folder.
3. Select **"New Terminal at Folder"**.

---

## Step 3 — Install dependencies (one time only)

In the terminal, type the following and press **Enter**:

```
pip install -r requirements.txt
```

Wait for it to finish — it may take a minute or two. You only need to do this once.

---

## Step 4 — Run the dashboard

In the terminal, type the following and press **Enter**:

```
python app.py
```

You will see some text appear. When it says **"Ready"**, open your web browser and go to:

```
http://127.0.0.1:8050
```

The dashboard will load. Keep the terminal window open while you use it.

---

## Step 5 — Stop the dashboard

When you are done, click back in the terminal window and press **Ctrl + C**.

---

## Using the dashboard

**Window size buttons** (`1s`, `5s`, `10m`, `All`, etc.)
Select how much time is shown at once across all plots. `All` shows the entire run.

**Slider**
When a window size is selected, drag the slider to move that window forward or backward through the run.

**Custom window**
Type any number of seconds in the `Custom` box and click **Set**.

**Panning the plots**
To drag the plots left and right with your mouse:
1. Hover over any plot — a small toolbar appears in the top-right corner.
2. Click the **hand icon** (pan mode).
3. Click and drag the plot left or right — all plots will follow together.

**Zooming**
Use the box-select or scroll wheel on any plot. Double-click a plot to reset its zoom.

---

## Troubleshooting

**"python is not recognized" or "pip is not recognized"**
Python was not added to PATH during installation. Uninstall Python and reinstall it, making sure to check the "Add Python to PATH" box.

**The browser shows "This site can't be reached"**
Make sure the terminal is still running `app.py` (you should see the "Ready" message). If you accidentally closed it, go back to Step 4.

**The page loads but shows no plots**
Wait a few seconds — the data can take a moment to load on slower computers.
