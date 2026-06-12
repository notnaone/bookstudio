async function jsonFetch(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

function createAdapter(format) {
  if (format === 'pdf') return new PdfAdapter();
  if (format === 'epub') return new EpubAdapter();
  if (format === 'txt' || format === 'docx') return new HtmlPagesAdapter();
  throw new Error(`Unsupported format: ${format}`);
}

class HtmlPagesAdapter {
  constructor() {
    this.book = null;
    this.container = null;
    this.iframe = null;
    this.currentPage = 1;
    this.totalPages = 0;
  }

  async init(container, book) {
    this.container = container;
    this.book = book;
    this.totalPages = book.pages || await this._probeTotalPages();
    this.currentPage = Math.max(1, book.current_page || 1);
    this.iframe = document.createElement('iframe');
    this.iframe.className = 'page-frame';
    this.iframe.title = book.title;
    container.innerHTML = '';
    container.appendChild(this.iframe);
    await this.goToPage(this.currentPage);
  }

  async _probeTotalPages() {
    let n = 1;
    while (n <= 10000) {
      const r = await fetch(
        `/api/books/${this.book.id}/view/page-${n}.html`,
        { method: 'HEAD' },
      );
      if (!r.ok) break;
      n += 1;
    }
    return Math.max(1, n - 1);
  }

  async goToPage(n) {
    const total = this.getTotalPages();
    this.currentPage = Math.min(Math.max(1, n), total || n);
    this.iframe.src =
      `/api/books/${this.book.id}/view/page-${this.currentPage}.html`;
  }

  getTotalPages() {
    return this.totalPages || this.book?.pages || 1;
  }

  getCurrentViewerPage() {
    return this.currentPage;
  }

  async search(query) {
    if (!query || !this.iframe.contentWindow) return;
    try {
      const doc = this.iframe.contentDocument;
      if (!doc || !doc.body) return;
      const text = doc.body.innerText || '';
      if (text.toLowerCase().includes(query.toLowerCase())) {
        doc.body.style.outline = '2px solid #4a9';
        setTimeout(() => { doc.body.style.outline = ''; }, 1500);
      }
    } catch (_) {
      /* cross-origin guard */
    }
  }
}

class PdfAdapter {
  constructor() {
    this.book = null;
    this.container = null;
    this.pdf = null;
    this.canvas = null;
    this.currentPage = 1;
    this._renderTask = null;
  }

  async init(container, book) {
    this.container = container;
    this.book = book;
    this.currentPage = Math.max(1, book.current_page || 1);
    container.innerHTML = '';
    this.canvas = document.createElement('canvas');
    this.canvas.className = 'page-frame';
    container.appendChild(this.canvas);
    const url = `/api/books/${book.id}/view/source`;
    this.pdf = await pdfjsLib.getDocument(url).promise;
    await this.goToPage(this.currentPage);
  }

  async goToPage(n) {
    if (!this.pdf) return;
    const total = this.getTotalPages();
    this.currentPage = Math.min(Math.max(1, n), total);
    const page = await this.pdf.getPage(this.currentPage);
    const viewport = page.getViewport({ scale: 1.25 });
    this.canvas.height = viewport.height;
    this.canvas.width = viewport.width;
    if (this._renderTask) {
      this._renderTask.cancel();
    }
    this._renderTask = page.render({
      canvasContext: this.canvas.getContext('2d'),
      viewport,
    });
    await this._renderTask.promise;
  }

  getTotalPages() {
    return this.pdf?.numPages || this.book?.pages || 1;
  }

  getCurrentViewerPage() {
    return this.currentPage;
  }

  async search(query) {
    if (!query || !this.pdf) return;
    const q = query.toLowerCase();
    for (let i = 1; i <= this.getTotalPages(); i += 1) {
      const page = await this.pdf.getPage(i);
      const content = await page.getTextContent();
      const text = content.items.map((it) => it.str).join(' ').toLowerCase();
      if (text.includes(q)) {
        await this.goToPage(i);
        this.canvas.style.outline = '2px solid #4a9';
        setTimeout(() => { this.canvas.style.outline = ''; }, 1500);
        return;
      }
    }
  }
}

class EpubAdapter {
  constructor() {
    this.book = null;
    this.container = null;
    this.rendition = null;
    this.bookObj = null;
    this.currentPage = 1;
    this.spineLength = 0;
  }

  async init(container, book) {
    this.container = container;
    this.book = book;
    this.currentPage = Math.max(1, book.current_page || 1);
    container.innerHTML = '';
    const url = `/api/books/${book.id}/view/source`;
    this.bookObj = ePub(url);
    await this.bookObj.ready;
    this.spineLength = this.bookObj.spine?.length || book.pages || 1;
    this.rendition = this.bookObj.renderTo(container, {
      width: '100%',
      height: '100%',
      flow: 'paginated',
    });
    this.rendition.on('relocated', (loc) => {
      const idx = loc?.start?.index;
      if (typeof idx === 'number') this.currentPage = idx + 1;
    });
    await this.goToPage(this.currentPage);
  }

  async goToPage(n) {
    if (!this.rendition) return;
    const total = this.getTotalPages();
    const page = Math.min(Math.max(1, n), total);
    this.currentPage = page;
    const spineIndex = page - 1;
    await this.rendition.display(spineIndex);
  }

  getTotalPages() {
    return this.book?.pages || this.spineLength || 1;
  }

  getCurrentViewerPage() {
    return this.currentPage;
  }

  async search(query) {
    if (!query || !this.bookObj) return;
    const results = await this.bookObj.search(query);
    if (results?.length) {
      await this.rendition.display(results[0].cfi);
    }
  }
}

function initLive() {
  /* session shell wired in follow-up commit */
}
