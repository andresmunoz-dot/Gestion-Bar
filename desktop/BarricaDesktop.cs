using System;
using System.Collections;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Net;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace BarricaDesktop
{
    internal static class Theme
    {
        public static readonly Color BgDark = Color.FromArgb(14, 27, 23);
        public static readonly Color BgCard = Color.FromArgb(21, 39, 31);
        public static readonly Color BgElevated = Color.FromArgb(29, 53, 42);
        public static readonly Color BgInput = Color.FromArgb(11, 22, 18);
        public static readonly Color BorderSubtle = Color.FromArgb(52, 74, 63);
        public static readonly Color TextBone = Color.FromArgb(239, 230, 210);
        public static readonly Color TextMuted = Color.FromArgb(163, 171, 157);
        public static readonly Color AccentAmber = Color.FromArgb(217, 164, 65);
        public static readonly Color AccentAmberLight = Color.FromArgb(232, 190, 106);
        public static readonly Color InkDark = Color.FromArgb(24, 20, 14);
        public static readonly Color StatusGreen = Color.FromArgb(76, 183, 130);
        public static readonly Color StatusRed = Color.FromArgb(229, 115, 104);

        private static Icon cachedIcon;

        public static Icon GetAppIcon()
        {
            if (cachedIcon != null) return cachedIcon;
            using (Bitmap bmp = new Bitmap(64, 64))
            using (Graphics g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.Clear(Color.Transparent);
                using (SolidBrush bg = new SolidBrush(BgDark))
                {
                    g.FillEllipse(bg, 2, 2, 60, 60);
                }
                using (Pen pOuter = new Pen(AccentAmber, 5f))
                using (Pen pInner = new Pen(TextBone, 2.2f))
                {
                    g.DrawEllipse(pOuter, 12, 12, 40, 40);
                    g.DrawEllipse(pInner, 20, 20, 24, 24);
                }
                IntPtr hIcon = bmp.GetHicon();
                cachedIcon = (Icon)Icon.FromHandle(hIcon).Clone();
            }
            return cachedIcon;
        }

        public static string Cop(object val)
        {
            long n = 0;
            if (val != null)
            {
                long.TryParse(Convert.ToString(val), out n);
            }
            return "$" + n.ToString("N0");
        }

        public static Button MakeButton(string text, bool primary, int width, int height)
        {
            Button btn = new Button();
            btn.Text = text;
            btn.Width = width;
            btn.Height = height;
            btn.FlatStyle = FlatStyle.Flat;
            btn.BackColor = primary ? AccentAmber : BgCard;
            btn.ForeColor = primary ? InkDark : TextBone;
            btn.Font = new Font("Segoe UI", 9.2f, primary ? FontStyle.Bold : FontStyle.Regular);
            btn.Cursor = Cursors.Hand;
            btn.FlatAppearance.BorderColor = primary ? AccentAmber : BorderSubtle;
            btn.FlatAppearance.BorderSize = 1;
            return btn;
        }
    }

    internal sealed class BufferedPanel : Panel
    {
        public BufferedPanel()
        {
            DoubleBuffered = true;
            ResizeRedraw = true;
        }
    }

    internal sealed class BufferedFlowPanel : FlowLayoutPanel
    {
        public BufferedFlowPanel()
        {
            DoubleBuffered = true;
            ResizeRedraw = true;
        }
    }

    internal sealed class BufferedListView : ListView
    {
        public BufferedListView()
        {
            DoubleBuffered = true;
        }
    }

    public sealed class SessionContext
    {
        public string ServerUrl = "http://127.0.0.1:5000";
        public string Token = "";
        public string UserName = "";
        public string UserEmail = "";
        public string UserRole = "vendedor";

        public bool IsAdmin
        {
            get { return string.Equals(UserRole, "administrador", StringComparison.OrdinalIgnoreCase); }
        }
    }

    internal static class LocalPrefs
    {
        private static string PrefsFilePath()
        {
            string dir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Barrica"
            );
            if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);
            return Path.Combine(dir, "desktop_prefs.json");
        }

        public static Dictionary<string, string> Load()
        {
            Dictionary<string, string> result = new Dictionary<string, string>();
            try
            {
                string path = PrefsFilePath();
                if (File.Exists(path))
                {
                    JavaScriptSerializer ser = new JavaScriptSerializer();
                    Dictionary<string, object> raw = ser.Deserialize<Dictionary<string, object>>(
                        File.ReadAllText(path, Encoding.UTF8)
                    );
                    if (raw != null)
                    {
                        foreach (KeyValuePair<string, object> kv in raw)
                        {
                            result[kv.Key] = Convert.ToString(kv.Value);
                        }
                    }
                }
            }
            catch { }
            return result;
        }

        public static void Save(string serverUrl, string email, string role)
        {
            try
            {
                JavaScriptSerializer ser = new JavaScriptSerializer();
                Dictionary<string, object> data = new Dictionary<string, object>();
                data["server_url"] = serverUrl;
                data["last_email"] = email;
                data["last_role"] = role;
                File.WriteAllText(PrefsFilePath(), ser.Serialize(data), Encoding.UTF8);
            }
            catch { }
        }
    }

    internal static class ApiClient
    {
        private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();

        static ApiClient()
        {
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            ServicePointManager.DefaultConnectionLimit = 12;
            ServicePointManager.Expect100Continue = false;
            ServicePointManager.UseNagleAlgorithm = false;
        }

        public static Dictionary<string, object> Request(
            string baseUrl,
            string token,
            string method,
            string path,
            object payload
        )
        {
            string cleanBase = (baseUrl ?? "http://127.0.0.1:5000").Trim().TrimEnd('/');
            HttpWebRequest req = (HttpWebRequest)WebRequest.Create(cleanBase + path);
            req.Method = method;
            req.Accept = "application/json";
            req.KeepAlive = true;
            req.Timeout = 9000;
            req.ReadWriteTimeout = 9000;
            req.AutomaticDecompression = DecompressionMethods.GZip | DecompressionMethods.Deflate;

            if (!string.IsNullOrEmpty(token))
            {
                req.Headers["Authorization"] = "Bearer " + token;
            }

            if (payload != null)
            {
                byte[] bytes = Encoding.UTF8.GetBytes(Json.Serialize(payload));
                req.ContentType = "application/json; charset=utf-8";
                req.ContentLength = bytes.Length;
                using (Stream reqStream = req.GetRequestStream())
                {
                    reqStream.Write(bytes, 0, bytes.Length);
                }
            }

            try
            {
                using (HttpWebResponse res = (HttpWebResponse)req.GetResponse())
                using (Stream resStream = res.GetResponseStream())
                {
                    if (resStream == null) return new Dictionary<string, object>();
                    using (StreamReader sr = new StreamReader(resStream, Encoding.UTF8))
                    {
                        string raw = sr.ReadToEnd();
                        if (string.IsNullOrEmpty(raw)) return new Dictionary<string, object>();
                        return Json.Deserialize<Dictionary<string, object>>(raw) ?? new Dictionary<string, object>();
                    }
                }
            }
            catch (WebException ex)
            {
                if (ex.Response != null)
                {
                    HttpWebResponse httpRes = ex.Response as HttpWebResponse;
                    using (Stream errStream = ex.Response.GetResponseStream())
                    {
                        if (errStream != null)
                        {
                            using (StreamReader sr = new StreamReader(errStream, Encoding.UTF8))
                            {
                                string errBody = sr.ReadToEnd();
                                try
                                {
                                    Dictionary<string, object> errObj = Json.Deserialize<Dictionary<string, object>>(errBody);
                                    if (errObj != null && errObj.ContainsKey("error"))
                                    {
                                        throw new ApplicationException(Convert.ToString(errObj["error"]));
                                    }
                                }
                                catch (InvalidOperationException) { }
                                catch (ArgumentException) { }
                            }
                        }
                    }
                    if (httpRes != null && httpRes.StatusCode == HttpStatusCode.Unauthorized)
                    {
                        throw new ApplicationException("Sesión no válida o expirada. Vuelve a iniciar sesión.");
                    }
                }
                throw new ApplicationException(
                    "Sin conexión con el servidor (" + cleanBase + "). Ejecuta .\\.venv\\Scripts\\python.exe app.py."
                );
            }
        }
    }

    public sealed class LoginForm : Form
    {
        private string selectedRole = "vendedor";
        private bool isRegisterMode = false;

        private BufferedPanel cardSeller;
        private BufferedPanel cardAdmin;
        private Label lblSellerTitle;
        private Label lblAdminTitle;

        private Panel pnlNameWrap;
        private TextBox txtName;
        private TextBox txtEmail;
        private TextBox txtPassword;
        private CheckBox chkShowPass;
        private TextBox txtServer;
        private Button btnSubmit;
        private Button btnSwitchMode;
        private Label lblStatus;
        private Label lblSubtitle;

        public SessionContext AuthenticatedSession { get; private set; }

        public LoginForm(string initialServerUrl)
        {
            Text = "Barrica · Iniciar Sesión";
            Icon = Theme.GetAppIcon();
            Size = new Size(530, 650);
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Theme.BgDark;
            ForeColor = Theme.TextBone;
            Font = new Font("Segoe UI", 9.5f, FontStyle.Regular);
            DoubleBuffered = true;

            Dictionary<string, string> prefs = LocalPrefs.Load();
            string savedServer = prefs.ContainsKey("server_url") && !string.IsNullOrEmpty(prefs["server_url"])
                ? prefs["server_url"]
                : (string.IsNullOrEmpty(initialServerUrl) ? "http://127.0.0.1:5000" : initialServerUrl);
            string savedEmail = prefs.ContainsKey("last_email") ? prefs["last_email"] : "";
            if (prefs.ContainsKey("last_role") && prefs["last_role"] == "administrador")
            {
                selectedRole = "administrador";
            }

            BuildUI(savedServer, savedEmail);
            UpdateModeAndRoleVisuals();
        }

        private void BuildUI(string savedServer, string savedEmail)
        {
            BufferedPanel card = new BufferedPanel();
            card.Location = new Point(24, 18);
            card.Size = new Size(466, 574);
            card.BackColor = Theme.BgCard;
            card.Padding = new Padding(22);

            Label lblBrand = new Label();
            lblBrand.Text = "BARRICA · SISTEMA DE BAR";
            lblBrand.Font = new Font("Georgia", 15.5f, FontStyle.Bold);
            lblBrand.ForeColor = Theme.AccentAmber;
            lblBrand.AutoSize = true;
            lblBrand.Location = new Point(22, 18);

            lblSubtitle = new Label();
            lblSubtitle.Text = "Paso 1: Elige tu perfil de trabajo e ingresa tus credenciales.";
            lblSubtitle.ForeColor = Theme.TextMuted;
            lblSubtitle.AutoSize = false;
            lblSubtitle.Size = new Size(420, 22);
            lblSubtitle.Location = new Point(22, 48);

            cardSeller = BuildRoleCard(
                "VENDEDOR",
                "Mesas, pedidos, división\nde cuentas y cobros",
                new Point(22, 80),
                out lblSellerTitle,
                delegate { selectedRole = "vendedor"; lblStatus.Text = ""; UpdateModeAndRoleVisuals(); }
            );

            cardAdmin = BuildRoleCard(
                "ADMINISTRADOR",
                "Acceso total: inventario,\nusuarios, sesiones y ventas",
                new Point(242, 80),
                out lblAdminTitle,
                delegate { selectedRole = "administrador"; lblStatus.Text = ""; UpdateModeAndRoleVisuals(); }
            );

            int y = 182;

            pnlNameWrap = new Panel();
            pnlNameWrap.Location = new Point(22, y);
            pnlNameWrap.Size = new Size(420, 56);
            Label lblName = new Label { Text = "Nombre completo (sin números):", ForeColor = Theme.TextBone, AutoSize = true, Location = new Point(0, 0) };
            txtName = MakeInput(new Point(0, 22), 420);
            pnlNameWrap.Controls.Add(lblName);
            pnlNameWrap.Controls.Add(txtName);

            Panel pnlCredentials = new Panel();
            pnlCredentials.Location = new Point(22, y);
            pnlCredentials.Size = new Size(420, 315);

            Label lblEmail = new Label { Text = "Correo electrónico:", ForeColor = Theme.TextBone, AutoSize = true, Location = new Point(0, 0) };
            txtEmail = MakeInput(new Point(0, 22), 420);
            txtEmail.Text = savedEmail;

            Label lblPass = new Label { Text = "Contraseña (mínimo 12 caracteres):", ForeColor = Theme.TextBone, AutoSize = true, Location = new Point(0, 62) };
            txtPassword = MakeInput(new Point(0, 84), 420);
            txtPassword.UseSystemPasswordChar = true;

            chkShowPass = new CheckBox();
            chkShowPass.Text = "Mostrar contraseña";
            chkShowPass.ForeColor = Theme.TextMuted;
            chkShowPass.AutoSize = true;
            chkShowPass.Location = new Point(0, 116);
            chkShowPass.CheckedChanged += delegate { txtPassword.UseSystemPasswordChar = !chkShowPass.Checked; };

            Label lblServer = new Label { Text = "Servidor Flask / MySQL:", ForeColor = Theme.TextMuted, AutoSize = true, Location = new Point(0, 148) };
            txtServer = MakeInput(new Point(0, 170), 420);
            txtServer.Text = savedServer;

            btnSubmit = Theme.MakeButton("INGRESAR COMO VENDEDOR", true, 420, 42);
            btnSubmit.Location = new Point(0, 212);
            btnSubmit.Font = new Font("Segoe UI", 10f, FontStyle.Bold);
            btnSubmit.Click += delegate { SubmitAuth(); };

            btnSwitchMode = new Button();
            btnSwitchMode.Text = "¿Nuevo integrante del equipo? Crear cuenta";
            btnSwitchMode.FlatStyle = FlatStyle.Flat;
            btnSwitchMode.FlatAppearance.BorderSize = 0;
            btnSwitchMode.BackColor = Theme.BgCard;
            btnSwitchMode.ForeColor = Theme.AccentAmberLight;
            btnSwitchMode.Cursor = Cursors.Hand;
            btnSwitchMode.Size = new Size(420, 28);
            btnSwitchMode.Location = new Point(0, 260);
            btnSwitchMode.Click += delegate
            {
                isRegisterMode = !isRegisterMode;
                lblStatus.Text = "";
                UpdateModeAndRoleVisuals();
            };

            pnlCredentials.Controls.AddRange(new Control[] {
                lblEmail, txtEmail, lblPass, txtPassword, chkShowPass, lblServer, txtServer, btnSubmit, btnSwitchMode
            });

            lblStatus = new Label();
            lblStatus.Text = "";
            lblStatus.ForeColor = Theme.StatusRed;
            lblStatus.AutoSize = false;
            lblStatus.Size = new Size(420, 44);
            lblStatus.Location = new Point(22, 520);

            card.Controls.AddRange(new Control[] {
                lblBrand, lblSubtitle, cardSeller, cardAdmin, pnlNameWrap, pnlCredentials, lblStatus
            });
            card.Tag = pnlCredentials;

            Controls.Add(card);
            AcceptButton = btnSubmit;
        }

        private BufferedPanel BuildRoleCard(
            string title,
            string desc,
            Point location,
            out Label titleLabel,
            EventHandler onClick
        )
        {
            BufferedPanel p = new BufferedPanel();
            p.Location = location;
            p.Size = new Size(200, 88);
            p.Cursor = Cursors.Hand;
            p.Padding = new Padding(10);

            Label t = new Label();
            t.Text = title;
            t.Font = new Font("Segoe UI", 10f, FontStyle.Bold);
            t.AutoSize = true;
            t.Location = new Point(12, 10);
            t.Cursor = Cursors.Hand;

            Label d = new Label();
            d.Text = desc;
            d.Font = new Font("Segoe UI", 8.3f, FontStyle.Regular);
            d.ForeColor = Theme.TextMuted;
            d.AutoSize = false;
            d.Size = new Size(176, 42);
            d.Location = new Point(12, 34);
            d.Cursor = Cursors.Hand;

            p.Click += onClick;
            t.Click += onClick;
            d.Click += onClick;

            p.Controls.Add(t);
            p.Controls.Add(d);
            titleLabel = t;
            return p;
        }

        private TextBox MakeInput(Point loc, int width)
        {
            TextBox tb = new TextBox();
            tb.Location = loc;
            tb.Width = width;
            tb.BackColor = Theme.BgInput;
            tb.ForeColor = Theme.TextBone;
            tb.BorderStyle = BorderStyle.FixedSingle;
            tb.Font = new Font("Segoe UI", 10f, FontStyle.Regular);
            return tb;
        }

        private void UpdateModeAndRoleVisuals()
        {
            bool seller = selectedRole == "vendedor";
            StyleRoleCard(cardSeller, lblSellerTitle, seller);
            StyleRoleCard(cardAdmin, lblAdminTitle, !seller);

            string roleLabel = seller ? "VENDEDOR" : "ADMINISTRADOR";
            Panel creds = (Panel)pnlNameWrap.Parent.Tag;

            if (isRegisterMode)
            {
                pnlNameWrap.Visible = true;
                creds.Location = new Point(22, 244);
                Size = new Size(530, 705);
                pnlNameWrap.Parent.Size = new Size(466, 628);
                lblStatus.Location = new Point(22, 568);
                lblSubtitle.Text = "Crear nueva cuenta con perfil de " + (seller ? "Vendedor." : "Administrador.");
                btnSubmit.Text = "CREAR CUENTA E INGRESAR (" + roleLabel + ")";
                btnSwitchMode.Text = "¿Ya tienes cuenta registrada? Iniciar sesión";
            }
            else
            {
                pnlNameWrap.Visible = false;
                creds.Location = new Point(22, 182);
                Size = new Size(530, 645);
                pnlNameWrap.Parent.Size = new Size(466, 568);
                lblStatus.Location = new Point(22, 506);
                lblSubtitle.Text = "Elige tu perfil de trabajo e ingresa tus credenciales.";
                btnSubmit.Text = "INGRESAR COMO " + roleLabel;
                btnSwitchMode.Text = "¿Nuevo integrante del equipo? Crear cuenta";
            }
        }

        private void StyleRoleCard(BufferedPanel panel, Label title, bool active)
        {
            panel.BackColor = active ? Theme.BgElevated : Theme.BgInput;
            title.ForeColor = active ? Theme.AccentAmberLight : Theme.TextBone;
            panel.Paint -= RoleCardPaintActive;
            panel.Paint -= RoleCardPaintInactive;
            panel.Paint += active ? new PaintEventHandler(RoleCardPaintActive) : new PaintEventHandler(RoleCardPaintInactive);
            panel.Invalidate();
        }

        private void RoleCardPaintActive(object sender, PaintEventArgs e)
        {
            Control c = (Control)sender;
            using (Pen p = new Pen(Theme.AccentAmber, 2f))
            {
                e.Graphics.DrawRectangle(p, 1, 1, c.Width - 3, c.Height - 3);
            }
        }

        private void RoleCardPaintInactive(object sender, PaintEventArgs e)
        {
            Control c = (Control)sender;
            using (Pen p = new Pen(Theme.BorderSubtle, 1f))
            {
                e.Graphics.DrawRectangle(p, 0, 0, c.Width - 1, c.Height - 1);
            }
        }

        private void SubmitAuth()
        {
            string email = txtEmail.Text.Trim();
            string password = txtPassword.Text;
            string name = txtName.Text.Trim();
            string serverUrl = txtServer.Text.Trim().TrimEnd('/');
            string role = selectedRole;
            bool register = isRegisterMode;

            if (string.IsNullOrEmpty(serverUrl))
            {
                lblStatus.ForeColor = Theme.StatusRed;
                lblStatus.Text = "Escribe la dirección del servidor (ej. http://127.0.0.1:5000).";
                return;
            }
            if (register)
            {
                if (name.Length < 2)
                {
                    lblStatus.ForeColor = Theme.StatusRed;
                    lblStatus.Text = "Escribe tu nombre completo.";
                    txtName.Focus();
                    return;
                }
                for (int i = 0; i < name.Length; i++)
                {
                    if (char.IsDigit(name[i]))
                    {
                        lblStatus.ForeColor = Theme.StatusRed;
                        lblStatus.Text = "El nombre no puede contener números.";
                        txtName.Focus();
                        return;
                    }
                }
            }
            if (string.IsNullOrEmpty(email) || !email.Contains("@"))
            {
                lblStatus.ForeColor = Theme.StatusRed;
                lblStatus.Text = "Escribe un correo electrónico válido.";
                txtEmail.Focus();
                return;
            }
            if (password.Length < 12)
            {
                lblStatus.ForeColor = Theme.StatusRed;
                lblStatus.Text = "La contraseña debe tener al menos 12 caracteres.";
                txtPassword.Focus();
                return;
            }

            btnSubmit.Enabled = false;
            lblStatus.ForeColor = Theme.AccentAmberLight;
            lblStatus.Text = "Verificando credenciales en MySQL...";

            Dictionary<string, object> payload = new Dictionary<string, object>();
            payload["email"] = email;
            payload["password"] = password;
            payload["role"] = role;
            if (register) payload["name"] = name;

            string endpoint = register ? "/api/auth/register" : "/api/auth/login";

            ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    Dictionary<string, object> res = ApiClient.Request(serverUrl, "", "POST", endpoint, payload);
                    Dictionary<string, object> user = res.ContainsKey("user")
                        ? res["user"] as Dictionary<string, object>
                        : null;
                    if (user == null)
                    {
                        throw new ApplicationException("El servidor no devolvió los datos del usuario.");
                    }

                    SessionContext ctx = new SessionContext();
                    ctx.ServerUrl = serverUrl;
                    ctx.Token = res.ContainsKey("token") ? Convert.ToString(res["token"]) : "";
                    ctx.UserName = Convert.ToString(user["name"]);
                    ctx.UserEmail = Convert.ToString(user["email"]);
                    ctx.UserRole = user.ContainsKey("role") ? Convert.ToString(user["role"]) : role;

                    LocalPrefs.Save(serverUrl, ctx.UserEmail, ctx.UserRole);

                    if (!IsDisposed && IsHandleCreated)
                    {
                        BeginInvoke((MethodInvoker)delegate
                        {
                            AuthenticatedSession = ctx;
                            DialogResult = DialogResult.OK;
                            Close();
                        });
                    }
                }
                catch (Exception ex)
                {
                    if (!IsDisposed && IsHandleCreated)
                    {
                        BeginInvoke((MethodInvoker)delegate
                        {
                            btnSubmit.Enabled = true;
                            lblStatus.ForeColor = Theme.StatusRed;
                            lblStatus.Text = ex.Message;
                        });
                    }
                }
            });
        }
    }

    public sealed class MainForm : Form
    {
        private readonly SessionContext session;
        private int isSyncing = 0;

        /* Navegación y barra superior */
        private Button btnNavSaloon;
        private Button btnNavInventory;
        private Button btnNavAdmin;
        private Label lblConnState;

        /* KPIs */
        private Label lblKpiSales;
        private Label lblKpiTables;
        private Label lblKpiStock;
        private Label lblKpiFourthVal;

        /* Vistas */
        private BufferedPanel viewSaloon;
        private BufferedPanel viewInventory;
        private BufferedPanel viewAdmin;

        /* Vista 1: Salón y Caja */
        private BufferedFlowPanel flowTables;
        private string tableStatusFilter = "all";
        private Button btnFilterAll;
        private Button btnFilterFree;
        private Button btnFilterBusy;
        private Button btnFilterBill;
        private Panel pnlAdminNewTable;
        private TextBox txtNewTableNum;
        private TextBox txtNewTableName;
        private NumericUpDown numNewTableCap;

        private Label lblSelTableName;
        private Label lblSelTableBadge;
        private Button btnDeleteFreeTable;
        private ComboBox cbOrderCatFilter;
        private ComboBox cbOrderProduct;
        private NumericUpDown numOrderQty;
        private BufferedListView lvOrders;
        private Label lblBigTotal;
        private NumericUpDown numSplitPeople;
        private Label lblSplitResult;
        private TextBox txtCashReceived;
        private Label lblCashChange;
        private ComboBox cbPayMethod;

        /* Vista 2: Carta e Inventario */
        private TextBox txtInvSearch;
        private ComboBox cbInvCategoryFilter;
        private BufferedListView lvProducts;
        private TextBox txtProdName;
        private ComboBox cbProdCategory;
        private TextBox txtProdPrice;
        private TextBox txtProdStock;
        private TextBox txtProdMin;

        /* Vista 3: Administración */
        private BufferedListView lvUsers;
        private BufferedListView lvSessions;
        private BufferedListView lvSales;

        /* Estado en memoria */
        private ArrayList currentTables = new ArrayList();
        private ArrayList currentProducts = new ArrayList();
        private int selectedTableId = 0;
        private System.Windows.Forms.Timer autoRefreshTimer;

        public bool LogoutRequested { get; private set; }

        internal MainForm(SessionContext ctx)
        {
            session = ctx;
            Text = "Barrica POS · " + session.UserName + " (" + (session.IsAdmin ? "Administrador" : "Vendedor") + ")";
            Icon = Theme.GetAppIcon();
            Size = new Size(1250, 790);
            MinimumSize = new Size(1040, 680);
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Theme.BgDark;
            ForeColor = Theme.TextBone;
            Font = new Font("Segoe UI", 9.5f, FontStyle.Regular);
            DoubleBuffered = true;
            KeyPreview = true;

            BuildMainLayout();
            SwitchModule("saloon");

            KeyDown += delegate(object s, KeyEventArgs e)
            {
                if (e.KeyCode == Keys.F5)
                {
                    e.Handled = true;
                    RefreshDashboardAsync(true);
                }
            };

            autoRefreshTimer = new System.Windows.Forms.Timer();
            autoRefreshTimer.Interval = 18000;
            autoRefreshTimer.Tick += delegate
            {
                if (WindowState != FormWindowState.Minimized)
                {
                    RefreshDashboardAsync(false);
                }
            };

            Shown += delegate
            {
                RefreshDashboardAsync(true);
                autoRefreshTimer.Start();
            };

            FormClosing += delegate
            {
                if (autoRefreshTimer != null) autoRefreshTimer.Stop();
            };
        }

        private void BuildMainLayout()
        {
            /* 1. Barra Superior */
            BufferedPanel topBar = new BufferedPanel();
            topBar.Dock = DockStyle.Top;
            topBar.Height = 62;
            topBar.BackColor = Theme.BgCard;

            Label lblLogo = new Label();
            lblLogo.Text = "BARRICA";
            lblLogo.Font = new Font("Georgia", 15f, FontStyle.Bold);
            lblLogo.ForeColor = Theme.AccentAmber;
            lblLogo.AutoSize = true;
            lblLogo.Location = new Point(18, 17);

            Label lblUserBadge = new Label();
            lblUserBadge.Text = session.UserName + " · " + (session.IsAdmin ? "ADMINISTRADOR" : "VENDEDOR");
            lblUserBadge.Font = new Font("Segoe UI", 8.5f, FontStyle.Bold);
            lblUserBadge.ForeColor = session.IsAdmin ? Theme.AccentAmberLight : Theme.StatusGreen;
            lblUserBadge.BackColor = Theme.BgElevated;
            lblUserBadge.AutoSize = true;
            lblUserBadge.Padding = new Padding(8, 4, 8, 4);
            lblUserBadge.Location = new Point(142, 20);

            /* Botones de módulos */
            int navX = 390;
            btnNavSaloon = Theme.MakeButton("1. Salón y Caja", true, 148, 36);
            btnNavSaloon.Location = new Point(navX, 13);
            btnNavSaloon.Click += delegate { SwitchModule("saloon"); };

            btnNavInventory = Theme.MakeButton(session.IsAdmin ? "2. Inventario MySQL" : "2. Carta y Stock", false, 165, 36);
            btnNavInventory.Location = new Point(navX + 156, 13);
            btnNavInventory.Click += delegate { SwitchModule("inventory"); };

            btnNavAdmin = Theme.MakeButton("3. Administración", false, 158, 36);
            btnNavAdmin.Location = new Point(navX + 329, 13);
            btnNavAdmin.Visible = session.IsAdmin;
            btnNavAdmin.Click += delegate { SwitchModule("admin"); };

            /* Acciones derechas */
            Button btnLogout = Theme.MakeButton("Cambiar usuario / Salir", false, 168, 34);
            btnLogout.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            btnLogout.Location = new Point(Width - 196, 14);
            btnLogout.ForeColor = Color.FromArgb(245, 165, 158);
            btnLogout.Click += delegate { PerformLogout(); };

            Button btnSync = Theme.MakeButton("Actualizar (F5)", false, 125, 34);
            btnSync.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            btnSync.Location = new Point(Width - 329, 14);
            btnSync.Click += delegate { RefreshDashboardAsync(true); };

            lblConnState = new Label();
            lblConnState.Text = "● Conectando...";
            lblConnState.ForeColor = Theme.AccentAmberLight;
            lblConnState.AutoSize = false;
            lblConnState.Size = new Size(190, 24);
            lblConnState.TextAlign = ContentAlignment.MiddleRight;
            lblConnState.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            lblConnState.Location = new Point(Width - 528, 19);

            topBar.Controls.AddRange(new Control[] {
                lblLogo, lblUserBadge, btnNavSaloon, btnNavInventory, btnNavAdmin, lblConnState, btnSync, btnLogout
            });

            /* 2. Tarjetas KPI Superiores */
            TableLayoutPanel kpiGrid = new TableLayoutPanel();
            kpiGrid.Dock = DockStyle.Top;
            kpiGrid.Height = 82;
            kpiGrid.ColumnCount = 4;
            kpiGrid.RowCount = 1;
            kpiGrid.Padding = new Padding(14, 10, 14, 6);
            kpiGrid.BackColor = Theme.BgDark;
            for (int i = 0; i < 4; i++)
            {
                kpiGrid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 25f));
            }

            Label dummy1, dummy2, dummy3, dummy4;
            kpiGrid.Controls.Add(MakeKpiCard("VENTAS DE HOY", "$0", out dummy1, out lblKpiSales), 0, 0);
            kpiGrid.Controls.Add(MakeKpiCard("MESAS ACTIVAS EN SALÓN", "0 / 0", out dummy2, out lblKpiTables), 1, 0);
            kpiGrid.Controls.Add(MakeKpiCard("ESTADO DE INVENTARIO", "Al día", out dummy3, out lblKpiStock), 2, 0);
            kpiGrid.Controls.Add(
                MakeKpiCard(
                    session.IsAdmin ? "SESIONES ACTIVAS" : "CUENTAS COBRADAS HOY",
                    "0",
                    out dummy4,
                    out lblKpiFourthVal
                ),
                3,
                0
            );

            /* 3. Contenedor Central de Vistas */
            BufferedPanel contentHost = new BufferedPanel();
            contentHost.Dock = DockStyle.Fill;
            contentHost.Padding = new Padding(14, 6, 14, 14);
            contentHost.BackColor = Theme.BgDark;

            viewSaloon = new BufferedPanel { Dock = DockStyle.Fill };
            viewInventory = new BufferedPanel { Dock = DockStyle.Fill, Visible = false };
            viewAdmin = new BufferedPanel { Dock = DockStyle.Fill, Visible = false };

            BuildSaloonView();
            BuildInventoryView();
            if (session.IsAdmin) BuildAdminView();

            contentHost.Controls.Add(viewSaloon);
            contentHost.Controls.Add(viewInventory);
            contentHost.Controls.Add(viewAdmin);

            Controls.Add(contentHost);
            Controls.Add(kpiGrid);
            Controls.Add(topBar);
        }

        private BufferedPanel MakeKpiCard(string title, string value, out Label titleOut, out Label valOut)
        {
            BufferedPanel p = new BufferedPanel();
            p.Dock = DockStyle.Fill;
            p.Margin = new Padding(4, 0, 4, 0);
            p.BackColor = Theme.BgCard;
            p.Padding = new Padding(12, 8, 12, 8);

            Label t = new Label();
            t.Text = title;
            t.Font = new Font("Segoe UI", 7.8f, FontStyle.Bold);
            t.ForeColor = Theme.TextMuted;
            t.AutoSize = true;
            t.Location = new Point(12, 8);

            Label v = new Label();
            v.Text = value;
            v.Font = new Font("Georgia", 15f, FontStyle.Bold);
            v.ForeColor = Theme.TextBone;
            v.AutoSize = true;
            v.Location = new Point(12, 28);

            p.Controls.Add(t);
            p.Controls.Add(v);
            titleOut = t;
            valOut = v;
            return p;
        }

        private void SwitchModule(string mod)
        {
            if (mod == "admin" && !session.IsAdmin) mod = "saloon";
            viewSaloon.Visible = (mod == "saloon");
            viewInventory.Visible = (mod == "inventory");
            viewAdmin.Visible = (mod == "admin");

            HighlightNavButton(btnNavSaloon, mod == "saloon");
            HighlightNavButton(btnNavInventory, mod == "inventory");
            HighlightNavButton(btnNavAdmin, mod == "admin");
        }

        private void HighlightNavButton(Button btn, bool active)
        {
            btn.BackColor = active ? Theme.AccentAmber : Theme.BgDark;
            btn.ForeColor = active ? Theme.InkDark : Theme.TextBone;
            btn.Font = new Font("Segoe UI", 9.2f, active ? FontStyle.Bold : FontStyle.Regular);
            btn.FlatAppearance.BorderColor = active ? Theme.AccentAmber : Theme.BorderSubtle;
        }

        /* ================= MÓDULO 1: SALÓN Y CAJA ================= */
        private void BuildSaloonView()
        {
            /* Panel derecho fijo para la cuenta y cobro */
            BufferedPanel rightOrderCard = new BufferedPanel();
            rightOrderCard.Dock = DockStyle.Right;
            rightOrderCard.Width = 456;
            rightOrderCard.BackColor = Theme.BgCard;
            rightOrderCard.Padding = new Padding(14);

            /* Panel izquierdo para tarjetas visuales de mesas */
            BufferedPanel leftTablesHost = new BufferedPanel();
            leftTablesHost.Dock = DockStyle.Fill;
            leftTablesHost.Padding = new Padding(0, 0, 12, 0);

            /* Barra superior izquierda: título + filtros de mesas */
            BufferedPanel filterBar = new BufferedPanel();
            filterBar.Dock = DockStyle.Top;
            filterBar.Height = 44;

            Label lblStep1 = new Label();
            lblStep1.Text = "Paso 1 · Selecciona una mesa:";
            lblStep1.Font = new Font("Georgia", 12f, FontStyle.Bold);
            lblStep1.ForeColor = Theme.TextBone;
            lblStep1.AutoSize = true;
            lblStep1.Location = new Point(2, 10);

            btnFilterAll = MakeFilterPill("Todas", new Point(255, 6), true, "all");
            btnFilterFree = MakeFilterPill("Libres", new Point(328, 6), false, "libre");
            btnFilterBusy = MakeFilterPill("Ocupadas", new Point(403, 6), false, "ocupada");
            btnFilterBill = MakeFilterPill("Por cobrar", new Point(494, 6), false, "por_cobrar");

            filterBar.Controls.AddRange(new Control[] { lblStep1, btnFilterAll, btnFilterFree, btnFilterBusy, btnFilterBill });

            /* Barra inferior izquierda (solo Admin): Crear nueva mesa con etiquetas claras */
            pnlAdminNewTable = new BufferedPanel();
            pnlAdminNewTable.Dock = DockStyle.Bottom;
            pnlAdminNewTable.Height = 62;
            pnlAdminNewTable.BackColor = Theme.BgCard;
            pnlAdminNewTable.Visible = session.IsAdmin;

            Label lNum = new Label { Text = "N.º Mesa", ForeColor = Theme.TextMuted, Font = new Font("Segoe UI", 8f), AutoSize = true, Location = new Point(10, 6) };
            txtNewTableNum = new TextBox { Location = new Point(10, 25), Width = 65, Text = "9", BackColor = Theme.BgInput, ForeColor = Theme.TextBone, BorderStyle = BorderStyle.FixedSingle };

            Label lNam = new Label { Text = "Nombre / Zona en salón", ForeColor = Theme.TextMuted, Font = new Font("Segoe UI", 8f), AutoSize = true, Location = new Point(85, 6) };
            txtNewTableName = new TextBox { Location = new Point(85, 25), Width = 215, Text = "Mesa 9 · Terraza", BackColor = Theme.BgInput, ForeColor = Theme.TextBone, BorderStyle = BorderStyle.FixedSingle };

            Label lCap = new Label { Text = "Puestos", ForeColor = Theme.TextMuted, Font = new Font("Segoe UI", 8f), AutoSize = true, Location = new Point(310, 6) };
            numNewTableCap = new NumericUpDown { Location = new Point(310, 25), Width = 65, Minimum = 1, Maximum = 50, Value = 4, BackColor = Theme.BgInput, ForeColor = Theme.TextBone };

            Button btnCreateTbl = Theme.MakeButton("+ Crear Mesa", true, 130, 30);
            btnCreateTbl.Location = new Point(388, 22);
            btnCreateTbl.Click += delegate { CreateTableAsync(); };

            pnlAdminNewTable.Controls.AddRange(new Control[] { lNum, txtNewTableNum, lNam, txtNewTableName, lCap, numNewTableCap, btnCreateTbl });

            flowTables = new BufferedFlowPanel();
            flowTables.Dock = DockStyle.Fill;
            flowTables.AutoScroll = true;
            flowTables.BackColor = Theme.BgDark;
            flowTables.Padding = new Padding(2, 6, 2, 6);

            leftTablesHost.Controls.Add(flowTables);
            leftTablesHost.Controls.Add(filterBar);
            leftTablesHost.Controls.Add(pnlAdminNewTable);

            /* Construcción del panel derecho (Comanda y Cobro) */
            Panel headPanel = new Panel { Dock = DockStyle.Top, Height = 56 };
            lblSelTableBadge = new Label
            {
                Text = "LIBRE",
                Font = new Font("Segoe UI", 8f, FontStyle.Bold),
                ForeColor = Theme.StatusGreen,
                AutoSize = true,
                Location = new Point(0, 0)
            };
            lblSelTableName = new Label
            {
                Text = "Selecciona una mesa",
                Font = new Font("Georgia", 14f, FontStyle.Bold),
                ForeColor = Theme.AccentAmberLight,
                AutoSize = true,
                Location = new Point(0, 20)
            };
            btnDeleteFreeTable = Theme.MakeButton("Eliminar mesa", false, 112, 28);
            btnDeleteFreeTable.Location = new Point(314, 14);
            btnDeleteFreeTable.ForeColor = Color.FromArgb(245, 165, 158);
            btnDeleteFreeTable.Visible = false;
            btnDeleteFreeTable.Click += delegate { DeleteSelectedTableAsync(); };
            headPanel.Controls.AddRange(new Control[] { lblSelTableBadge, lblSelTableName, btnDeleteFreeTable });

            /* Paso 2: Agregar productos */
            Panel addPanel = new Panel { Dock = DockStyle.Top, Height = 96 };
            Label lblStep2 = new Label
            {
                Text = "Paso 2 · Agregar bebida o plato a la cuenta:",
                Font = new Font("Segoe UI", 8.8f, FontStyle.Bold),
                ForeColor = Theme.TextMuted,
                AutoSize = true,
                Location = new Point(0, 2)
            };

            cbOrderCatFilter = new ComboBox
            {
                DropDownStyle = ComboBoxStyle.DropDownList,
                Location = new Point(0, 24),
                Width = 140,
                BackColor = Theme.BgInput,
                ForeColor = Theme.TextBone
            };
            cbOrderCatFilter.Items.AddRange(new object[] { "Todas", "Cócteles", "Cervezas", "Licores", "Comida", "Sin alcohol" });
            cbOrderCatFilter.SelectedIndex = 0;
            cbOrderCatFilter.SelectedIndexChanged += delegate { PopulateOrderProductCombo(); };

            cbOrderProduct = new ComboBox
            {
                DropDownStyle = ComboBoxStyle.DropDownList,
                Location = new Point(146, 24),
                Width = 280,
                BackColor = Theme.BgInput,
                ForeColor = Theme.TextBone
            };

            Label lblQty = new Label { Text = "Cantidad:", ForeColor = Theme.TextMuted, AutoSize = true, Location = new Point(0, 62) };
            Button btnQtyMinus = Theme.MakeButton("-", false, 32, 28);
            btnQtyMinus.Location = new Point(66, 58);
            btnQtyMinus.Click += delegate { if (numOrderQty.Value > 1) numOrderQty.Value -= 1; };

            numOrderQty = new NumericUpDown
            {
                Minimum = 1,
                Maximum = 99,
                Value = 1,
                Width = 54,
                Location = new Point(102, 60),
                TextAlign = HorizontalAlignment.Center,
                BackColor = Theme.BgInput,
                ForeColor = Theme.TextBone
            };

            Button btnQtyPlus = Theme.MakeButton("+", false, 32, 28);
            btnQtyPlus.Location = new Point(160, 58);
            btnQtyPlus.Click += delegate { if (numOrderQty.Value < 99) numOrderQty.Value += 1; };

            Button btnAddOrder = Theme.MakeButton("+ Agregar a la mesa", true, 224, 30);
            btnAddOrder.Location = new Point(202, 57);
            btnAddOrder.Click += delegate { AddOrderToTableAsync(); };

            addPanel.Controls.AddRange(new Control[] {
                lblStep2, cbOrderCatFilter, cbOrderProduct, lblQty, btnQtyMinus, numOrderQty, btnQtyPlus, btnAddOrder
            });

            /* Paso 3: Calculadora de Cobro (Abajo) */
            Panel checkoutPanel = new Panel { Dock = DockStyle.Bottom, Height = 216, Padding = new Padding(0, 8, 0, 0) };

            Button btnRemoveItem = Theme.MakeButton("Quitar producto seleccionado", false, 215, 28);
            btnRemoveItem.Location = new Point(0, 4);
            btnRemoveItem.ForeColor = Color.FromArgb(245, 165, 158);
            btnRemoveItem.Click += delegate { RemoveSelectedOrderAsync(); };

            Label lblTotalCap = new Label { Text = "TOTAL MESA:", Font = new Font("Segoe UI", 9f, FontStyle.Bold), ForeColor = Theme.TextMuted, AutoSize = true, Location = new Point(0, 42) };
            lblBigTotal = new Label { Text = "$0", Font = new Font("Georgia", 18f, FontStyle.Bold), ForeColor = Theme.AccentAmberLight, AutoSize = true, Location = new Point(105, 34) };

            Label lblSplit = new Label { Text = "Dividir entre personas:", ForeColor = Theme.TextMuted, AutoSize = true, Location = new Point(0, 78) };
            numSplitPeople = new NumericUpDown { Minimum = 1, Maximum = 30, Value = 1, Width = 54, Location = new Point(148, 75), BackColor = Theme.BgInput, ForeColor = Theme.TextBone };
            numSplitPeople.ValueChanged += delegate { UpdateSplitAndChange(); };
            lblSplitResult = new Label { Text = "$0 c/u", Font = new Font("Segoe UI", 9.5f, FontStyle.Bold), ForeColor = Theme.TextBone, AutoSize = true, Location = new Point(212, 77) };

            Label lblCash = new Label { Text = "Efectivo recibido ($):", ForeColor = Theme.TextMuted, AutoSize = true, Location = new Point(0, 110) };
            txtCashReceived = new TextBox { Width = 105, Location = new Point(148, 107), BackColor = Theme.BgInput, ForeColor = Theme.TextBone, BorderStyle = BorderStyle.FixedSingle };
            txtCashReceived.TextChanged += delegate { UpdateSplitAndChange(); };
            lblCashChange = new Label { Text = "Cambio: $0", Font = new Font("Segoe UI", 9.2f, FontStyle.Bold), ForeColor = Theme.StatusGreen, AutoSize = true, Location = new Point(262, 109) };

            Label lblPayM = new Label { Text = "Medio de pago:", ForeColor = Theme.TextMuted, AutoSize = true, Location = new Point(0, 142) };
            cbPayMethod = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Width = 200, Location = new Point(148, 138), BackColor = Theme.BgInput, ForeColor = Theme.TextBone };
            cbPayMethod.Items.AddRange(new object[] { "Efectivo", "Tarjeta", "Transferencia / Nequi" });
            cbPayMethod.SelectedIndex = 0;

            Button btnMarkBill = Theme.MakeButton("Pedir cuenta", false, 140, 38);
            btnMarkBill.Location = new Point(0, 174);
            btnMarkBill.Click += delegate { MarkTableForBillAsync(); };

            Button btnCheckout = Theme.MakeButton("COBRAR Y LIBERAR MESA", true, 276, 38);
            btnCheckout.Location = new Point(150, 174);
            btnCheckout.Click += delegate { CheckoutTableAsync(); };

            checkoutPanel.Controls.AddRange(new Control[] {
                btnRemoveItem, lblTotalCap, lblBigTotal,
                lblSplit, numSplitPeople, lblSplitResult,
                lblCash, txtCashReceived, lblCashChange,
                lblPayM, cbPayMethod, btnMarkBill, btnCheckout
            });

            lvOrders = MakeListView(
                new string[] { "Cant.", "Producto", "Unitario", "Subtotal" },
                new int[] { 55, 190, 85, 92 }
            );

            rightOrderCard.Controls.Add(lvOrders);
            rightOrderCard.Controls.Add(addPanel);
            rightOrderCard.Controls.Add(headPanel);
            rightOrderCard.Controls.Add(checkoutPanel);

            viewSaloon.Controls.Add(leftTablesHost);
            viewSaloon.Controls.Add(rightOrderCard);
        }

        private Button MakeFilterPill(string text, Point loc, bool active, string filterValue)
        {
            Button b = Theme.MakeButton(text, active, text.Length > 7 ? 92 : 70, 28);
            b.Location = loc;
            b.Font = new Font("Segoe UI", 8.3f, active ? FontStyle.Bold : FontStyle.Regular);
            b.Click += delegate
            {
                tableStatusFilter = filterValue;
                HighlightNavButton(btnFilterAll, filterValue == "all");
                HighlightNavButton(btnFilterFree, filterValue == "libre");
                HighlightNavButton(btnFilterBusy, filterValue == "ocupada");
                HighlightNavButton(btnFilterBill, filterValue == "por_cobrar");
                RenderTablesCards();
            };
            return b;
        }

        /* ================= MÓDULO 2: CARTA E INVENTARIO ================= */
        private void BuildInventoryView()
        {
            BufferedPanel topSearchPanel = new BufferedPanel();
            topSearchPanel.Dock = DockStyle.Top;
            topSearchPanel.Height = session.IsAdmin ? 54 : 84;
            topSearchPanel.BackColor = Theme.BgCard;
            topSearchPanel.Padding = new Padding(10);

            Label lblS = new Label { Text = "Buscar producto:", ForeColor = Theme.TextMuted, AutoSize = true, Location = new Point(12, 16) };
            txtInvSearch = new TextBox { Location = new Point(122, 13), Width = 230, BackColor = Theme.BgInput, ForeColor = Theme.TextBone, BorderStyle = BorderStyle.FixedSingle };
            txtInvSearch.TextChanged += delegate { RenderInventoryList(); };

            Label lblCatF = new Label { Text = "Categoría:", ForeColor = Theme.TextMuted, AutoSize = true, Location = new Point(368, 16) };
            cbInvCategoryFilter = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Location = new Point(440, 12), Width = 155, BackColor = Theme.BgInput, ForeColor = Theme.TextBone };
            cbInvCategoryFilter.Items.AddRange(new object[] { "Todas", "Licores", "Cócteles", "Cervezas", "Comida", "Sin alcohol" });
            cbInvCategoryFilter.SelectedIndex = 0;
            cbInvCategoryFilter.SelectedIndexChanged += delegate { RenderInventoryList(); };

            topSearchPanel.Controls.AddRange(new Control[] { lblS, txtInvSearch, lblCatF, cbInvCategoryFilter });

            if (session.IsAdmin)
            {
                Button btnMinus1 = Theme.MakeButton("-1 Stock", false, 88, 30);
                btnMinus1.Location = new Point(615, 11);
                btnMinus1.Click += delegate { AdjustSelectedStockAsync(-1); };

                Button btnPlus1 = Theme.MakeButton("+1 Stock", false, 88, 30);
                btnPlus1.Location = new Point(710, 11);
                btnPlus1.Click += delegate { AdjustSelectedStockAsync(1); };

                Button btnPlus10 = Theme.MakeButton("+10 Botellas", false, 110, 30);
                btnPlus10.Location = new Point(805, 11);
                btnPlus10.Click += delegate { AdjustSelectedStockAsync(10); };

                Button btnDeleteProd = Theme.MakeButton("Eliminar producto", false, 148, 30);
                btnDeleteProd.Location = new Point(922, 11);
                btnDeleteProd.ForeColor = Color.FromArgb(245, 165, 158);
                btnDeleteProd.Click += delegate { DeleteSelectedProductAsync(); };

                topSearchPanel.Controls.AddRange(new Control[] { btnMinus1, btnPlus1, btnPlus10, btnDeleteProd });
            }
            else
            {
                Label lblSellerInfo = new Label();
                lblSellerInfo.Text = "Modo Vendedor · Consulta en vivo de precios y unidades disponibles en barra. La edición de stock está reservada al Administrador.";
                lblSellerInfo.ForeColor = Theme.StatusGreen;
                lblSellerInfo.AutoSize = true;
                lblSellerInfo.Location = new Point(12, 50);
                topSearchPanel.Controls.Add(lblSellerInfo);
            }

            if (session.IsAdmin)
            {
                BufferedPanel bottomAddProd = new BufferedPanel();
                bottomAddProd.Dock = DockStyle.Bottom;
                bottomAddProd.Height = 68;
                bottomAddProd.BackColor = Theme.BgCard;

                Label p1 = new Label { Text = "Nuevo producto", ForeColor = Theme.TextMuted, Font = new Font("Segoe UI", 8f), AutoSize = true, Location = new Point(12, 8) };
                txtProdName = new TextBox { Location = new Point(12, 28), Width = 250, Text = "Whisky Old Parr 12", BackColor = Theme.BgInput, ForeColor = Theme.TextBone, BorderStyle = BorderStyle.FixedSingle };

                Label p2 = new Label { Text = "Categoría", ForeColor = Theme.TextMuted, Font = new Font("Segoe UI", 8f), AutoSize = true, Location = new Point(272, 8) };
                cbProdCategory = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Location = new Point(272, 27), Width = 140, BackColor = Theme.BgInput, ForeColor = Theme.TextBone };
                cbProdCategory.Items.AddRange(new object[] { "Licores", "Cócteles", "Cervezas", "Comida", "Sin alcohol" });
                cbProdCategory.SelectedIndex = 0;

                Label p3 = new Label { Text = "Precio COP", ForeColor = Theme.TextMuted, Font = new Font("Segoe UI", 8f), AutoSize = true, Location = new Point(422, 8) };
                txtProdPrice = new TextBox { Location = new Point(422, 28), Width = 110, Text = "185000", BackColor = Theme.BgInput, ForeColor = Theme.TextBone, BorderStyle = BorderStyle.FixedSingle };

                Label p4 = new Label { Text = "Stock inicial", ForeColor = Theme.TextMuted, Font = new Font("Segoe UI", 8f), AutoSize = true, Location = new Point(542, 8) };
                txtProdStock = new TextBox { Location = new Point(542, 28), Width = 85, Text = "12", BackColor = Theme.BgInput, ForeColor = Theme.TextBone, BorderStyle = BorderStyle.FixedSingle };

                Label p5 = new Label { Text = "Alerta mín.", ForeColor = Theme.TextMuted, Font = new Font("Segoe UI", 8f), AutoSize = true, Location = new Point(637, 8) };
                txtProdMin = new TextBox { Location = new Point(637, 28), Width = 85, Text = "4", BackColor = Theme.BgInput, ForeColor = Theme.TextBone, BorderStyle = BorderStyle.FixedSingle };

                Button btnSaveProd = Theme.MakeButton("+ Guardar Producto en MySQL", true, 235, 32);
                btnSaveProd.Location = new Point(736, 24);
                btnSaveProd.Click += delegate { CreateProductAsync(); };

                bottomAddProd.Controls.AddRange(new Control[] {
                    p1, txtProdName, p2, cbProdCategory, p3, txtProdPrice, p4, txtProdStock, p5, txtProdMin, btnSaveProd
                });
                viewInventory.Controls.Add(bottomAddProd);
            }

            lvProducts = MakeListView(
                new string[] { "ID", "Producto", "Categoría", "Precio Venta (COP)", "Existencias", "Mínimo Alerta", "Estado" },
                new int[] { 55, 300, 150, 155, 120, 120, 160 }
            );

            viewInventory.Controls.Add(lvProducts);
            viewInventory.Controls.Add(topSearchPanel);
        }

        /* ================= MÓDULO 3: ADMINISTRACIÓN ================= */
        private void BuildAdminView()
        {
            TableLayoutPanel grid = new TableLayoutPanel();
            grid.Dock = DockStyle.Fill;
            grid.ColumnCount = 2;
            grid.RowCount = 2;
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 52f));
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 48f));
            grid.RowStyles.Add(new RowStyle(SizeType.Percent, 52f));
            grid.RowStyles.Add(new RowStyle(SizeType.Percent, 48f));

            GroupBox grpUsers = MakeGroup("Equipo y Roles de Usuarios (MySQL: users)");
            Panel usrActions = new Panel { Dock = DockStyle.Top, Height = 36 };
            Button btnToggleRole = Theme.MakeButton("Cambiar rol del usuario seleccionado (Admin ↔ Vendedor)", true, 360, 28);
            btnToggleRole.Location = new Point(0, 4);
            btnToggleRole.Click += delegate { ToggleSelectedUserRoleAsync(); };
            usrActions.Controls.Add(btnToggleRole);

            lvUsers = MakeListView(
                new string[] { "ID", "Nombre", "Correo", "Perfil Actual", "Registro (UTC)" },
                new int[] { 45, 130, 175, 110, 135 }
            );
            grpUsers.Controls.Add(lvUsers);
            grpUsers.Controls.Add(usrActions);

            GroupBox grpSessions = MakeGroup("Inicios de Sesión Registrados (MySQL: sessions)");
            lvSessions = MakeListView(
                new string[] { "Usuario", "Correo", "Perfil", "Inicio (UTC)", "Estado" },
                new int[] { 115, 155, 95, 135, 80 }
            );
            grpSessions.Controls.Add(lvSessions);

            GroupBox grpSales = MakeGroup("Historial de Ventas Cobradas (MySQL: sales)");
            lvSales = MakeListView(
                new string[] { "Ticket", "Mesa", "Detalle de Consumo", "Medio de Pago", "Total COP", "Fecha (UTC)" },
                new int[] { 65, 165, 430, 150, 130, 165 }
            );
            grpSales.Controls.Add(lvSales);

            grid.Controls.Add(grpUsers, 0, 0);
            grid.Controls.Add(grpSessions, 1, 0);
            grid.Controls.Add(grpSales, 0, 1);
            grid.SetColumnSpan(grpSales, 2);

            viewAdmin.Controls.Add(grid);
        }

        private GroupBox MakeGroup(string title)
        {
            GroupBox g = new GroupBox();
            g.Text = title;
            g.Dock = DockStyle.Fill;
            g.ForeColor = Theme.AccentAmberLight;
            g.BackColor = Theme.BgCard;
            g.Padding = new Padding(10);
            return g;
        }

        private BufferedListView MakeListView(string[] headers, int[] widths)
        {
            BufferedListView lv = new BufferedListView();
            lv.Dock = DockStyle.Fill;
            lv.View = View.Details;
            lv.FullRowSelect = true;
            lv.GridLines = true;
            lv.BackColor = Theme.BgInput;
            lv.ForeColor = Theme.TextBone;
            lv.BorderStyle = BorderStyle.FixedSingle;
            for (int i = 0; i < headers.Length; i++)
            {
                lv.Columns.Add(headers[i], widths[i]);
            }
            return lv;
        }

        /* ================= RENDERIZADO Y LÓGICA ASÍNCRONA ================= */
        private void RefreshDashboardAsync(bool showSyncText)
        {
            if (Interlocked.CompareExchange(ref isSyncing, 1, 0) != 0) return;

            if (showSyncText)
            {
                lblConnState.ForeColor = Theme.AccentAmberLight;
                lblConnState.Text = "● Sincronizando...";
            }

            ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    Dictionary<string, object> data = ApiClient.Request(
                        session.ServerUrl,
                        session.Token,
                        "GET",
                        "/api/bar/dashboard",
                        null
                    );

                    if (!IsDisposed && IsHandleCreated)
                    {
                        BeginInvoke((MethodInvoker)delegate
                        {
                            ApplyDashboardData(data);
                        });
                    }
                }
                catch (Exception ex)
                {
                    if (!IsDisposed && IsHandleCreated)
                    {
                        BeginInvoke((MethodInvoker)delegate
                        {
                            lblConnState.ForeColor = Theme.StatusRed;
                            lblConnState.Text = "● Error de conexión";
                            if (showSyncText)
                            {
                                MessageBox.Show(ex.Message, "Barrica POS", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                            }
                        });
                    }
                }
                finally
                {
                    Interlocked.Exchange(ref isSyncing, 0);
                }
            });
        }

        private void ApplyDashboardData(Dictionary<string, object> data)
        {
            currentTables = data.ContainsKey("tables") ? (data["tables"] as ArrayList ?? new ArrayList()) : new ArrayList();
            currentProducts = data.ContainsKey("products") ? (data["products"] as ArrayList ?? new ArrayList()) : new ArrayList();
            Dictionary<string, object> admin = data.ContainsKey("admin")
                ? (data["admin"] as Dictionary<string, object> ?? new Dictionary<string, object>())
                : new Dictionary<string, object>();

            int occupied = 0;
            bool selectedStillExists = false;
            foreach (Dictionary<string, object> t in currentTables)
            {
                int id = Convert.ToInt32(t["id"]);
                if (Convert.ToString(t["status"]) != "libre") occupied++;
                if (id == selectedTableId) selectedStillExists = true;
            }
            if ((!selectedStillExists || selectedTableId == 0) && currentTables.Count > 0)
            {
                Dictionary<string, object> first = (Dictionary<string, object>)currentTables[0];
                selectedTableId = Convert.ToInt32(first["id"]);
            }

            int lowStock = 0;
            foreach (Dictionary<string, object> p in currentProducts)
            {
                if (Convert.ToBoolean(p["low_stock"])) lowStock++;
            }

            lblKpiSales.Text = Theme.Cop(admin.ContainsKey("sales_today_cop") ? admin["sales_today_cop"] : 0);
            lblKpiTables.Text = occupied + " de " + currentTables.Count + " ocupadas";
            lblKpiStock.Text = lowStock > 0 ? (lowStock + " con stock bajo") : "Todo al día";
            lblKpiStock.ForeColor = lowStock > 0 ? Theme.StatusRed : Theme.StatusGreen;

            if (session.IsAdmin)
            {
                ArrayList sessions = admin.ContainsKey("sessions") ? admin["sessions"] as ArrayList : null;
                int activeCount = 0;
                if (sessions != null)
                {
                    foreach (Dictionary<string, object> s in sessions)
                    {
                        if (Convert.ToBoolean(s["active"])) activeCount++;
                    }
                }
                lblKpiFourthVal.Text = activeCount.ToString();
                RenderAdminTables(admin);
            }
            else
            {
                lblKpiFourthVal.Text = Convert.ToString(admin.ContainsKey("sales_count_today") ? admin["sales_count_today"] : 0);
            }

            RenderTablesCards();
            PopulateOrderProductCombo();
            RenderSelectedTableDetails();
            RenderInventoryList();

            lblConnState.ForeColor = Theme.StatusGreen;
            lblConnState.Text = "● En línea · " + DateTime.Now.ToString("HH:mm:ss");
        }

        private void RenderTablesCards()
        {
            flowTables.SuspendLayout();
            flowTables.Controls.Clear();

            foreach (Dictionary<string, object> t in currentTables)
            {
                string st = Convert.ToString(t["status"]);
                if (tableStatusFilter != "all" && st != tableStatusFilter) continue;

                int tid = Convert.ToInt32(t["id"]);
                bool isSel = (tid == selectedTableId);
                ArrayList orders = t["orders"] as ArrayList ?? new ArrayList();

                BufferedPanel card = new BufferedPanel();
                card.Size = new Size(182, 112);
                card.Margin = new Padding(0, 0, 10, 10);
                card.BackColor = isSel ? Theme.BgElevated : Theme.BgCard;
                card.Cursor = Cursors.Hand;

                Color badgeColor = Theme.StatusGreen;
                string badgeText = "● LIBRE";
                if (st == "ocupada") { badgeColor = Theme.AccentAmberLight; badgeText = "● OCUPADA"; }
                else if (st == "por_cobrar") { badgeColor = Theme.StatusRed; badgeText = "● POR COBRAR"; }

                Label lBadge = new Label
                {
                    Text = badgeText,
                    Font = new Font("Segoe UI", 7.8f, FontStyle.Bold),
                    ForeColor = badgeColor,
                    AutoSize = true,
                    Location = new Point(12, 10),
                    Cursor = Cursors.Hand
                };

                Label lTitle = new Label
                {
                    Text = Convert.ToString(t["label"]),
                    Font = new Font("Segoe UI", 10f, FontStyle.Bold),
                    ForeColor = Theme.TextBone,
                    AutoSize = false,
                    Size = new Size(158, 22),
                    Location = new Point(12, 32),
                    Cursor = Cursors.Hand
                };

                Label lMeta = new Label
                {
                    Text = Convert.ToString(t["capacity"]) + " puestos · " + orders.Count + " ítems",
                    Font = new Font("Segoe UI", 8.2f, FontStyle.Regular),
                    ForeColor = Theme.TextMuted,
                    AutoSize = true,
                    Location = new Point(12, 56),
                    Cursor = Cursors.Hand
                };

                long total = Convert.ToInt64(t["total_cop"] ?? 0);
                Label lTotal = new Label
                {
                    Text = total > 0 ? Theme.Cop(total) : "Disponible",
                    Font = new Font("Georgia", 11.5f, FontStyle.Bold),
                    ForeColor = total > 0 ? Theme.AccentAmberLight : Theme.StatusGreen,
                    AutoSize = true,
                    Location = new Point(12, 79),
                    Cursor = Cursors.Hand
                };

                int capturedId = tid;
                EventHandler selectHandler = delegate
                {
                    selectedTableId = capturedId;
                    RenderTablesCards();
                    RenderSelectedTableDetails();
                };

                card.Click += selectHandler;
                lBadge.Click += selectHandler;
                lTitle.Click += selectHandler;
                lMeta.Click += selectHandler;
                lTotal.Click += selectHandler;

                bool capturedSel = isSel;
                card.Paint += delegate(object sender, PaintEventArgs e)
                {
                    Control c = (Control)sender;
                    using (Pen pen = new Pen(capturedSel ? Theme.AccentAmber : Theme.BorderSubtle, capturedSel ? 2f : 1f))
                    {
                        int offset = capturedSel ? 1 : 0;
                        int sub = capturedSel ? 3 : 1;
                        e.Graphics.DrawRectangle(pen, offset, offset, c.Width - sub, c.Height - sub);
                    }
                };

                card.Controls.AddRange(new Control[] { lBadge, lTitle, lMeta, lTotal });
                flowTables.Controls.Add(card);
            }

            flowTables.ResumeLayout();
        }

        private void PopulateOrderProductCombo()
        {
            int previousId = 0;
            ProductComboItem prevItem = cbOrderProduct.SelectedItem as ProductComboItem;
            if (prevItem != null) previousId = prevItem.Id;

            string cat = cbOrderCatFilter.SelectedItem != null ? Convert.ToString(cbOrderCatFilter.SelectedItem) : "Todas";

            cbOrderProduct.BeginUpdate();
            cbOrderProduct.Items.Clear();
            int idxToSelect = 0;
            int currentIdx = 0;

            foreach (Dictionary<string, object> p in currentProducts)
            {
                string pCat = Convert.ToString(p["category"]);
                int stock = Convert.ToInt32(p["stock"]);
                if (cat != "Todas" && pCat != cat) continue;
                if (stock <= 0) continue;

                int pid = Convert.ToInt32(p["id"]);
                cbOrderProduct.Items.Add(new ProductComboItem
                {
                    Id = pid,
                    Display = Convert.ToString(p["name"]) + " · " + Theme.Cop(p["price_cop"]) + " (" + stock + " disp.)"
                });
                if (pid == previousId) idxToSelect = currentIdx;
                currentIdx++;
            }

            if (cbOrderProduct.Items.Count > 0) cbOrderProduct.SelectedIndex = idxToSelect;
            cbOrderProduct.EndUpdate();
        }

        private void RenderSelectedTableDetails()
        {
            lvOrders.BeginUpdate();
            lvOrders.Items.Clear();

            Dictionary<string, object> active = null;
            foreach (Dictionary<string, object> t in currentTables)
            {
                if (Convert.ToInt32(t["id"]) == selectedTableId)
                {
                    active = t;
                    break;
                }
            }

            if (active == null)
            {
                lblSelTableBadge.Text = "SIN SELECCIÓN";
                lblSelTableName.Text = "Selecciona una mesa";
                lblBigTotal.Text = "$0";
                btnDeleteFreeTable.Visible = false;
                lvOrders.EndUpdate();
                UpdateSplitAndChange();
                return;
            }

            string st = Convert.ToString(active["status"]);
            lblSelTableName.Text = Convert.ToString(active["label"]);
            if (st == "libre") { lblSelTableBadge.Text = "● MESA LIBRE"; lblSelTableBadge.ForeColor = Theme.StatusGreen; }
            else if (st == "ocupada") { lblSelTableBadge.Text = "● MESA OCUPADA"; lblSelTableBadge.ForeColor = Theme.AccentAmberLight; }
            else { lblSelTableBadge.Text = "● CUENTA SOLICITADA"; lblSelTableBadge.ForeColor = Theme.StatusRed; }

            ArrayList orders = active["orders"] as ArrayList ?? new ArrayList();
            btnDeleteFreeTable.Visible = session.IsAdmin && orders.Count == 0;

            foreach (Dictionary<string, object> o in orders)
            {
                ListViewItem item = new ListViewItem(new string[] {
                    Convert.ToString(o["quantity"]) + "x",
                    Convert.ToString(o["product_name"]),
                    Theme.Cop(o["unit_price_cop"]),
                    Theme.Cop(o["subtotal_cop"])
                });
                item.Tag = Convert.ToInt32(o["id"]);
                lvOrders.Items.Add(item);
            }

            lblBigTotal.Text = Theme.Cop(active["total_cop"]);
            lblBigTotal.Tag = Convert.ToInt64(active["total_cop"] ?? 0);
            lvOrders.EndUpdate();
            UpdateSplitAndChange();
        }

        private void UpdateSplitAndChange()
        {
            long total = lblBigTotal.Tag != null ? Convert.ToInt64(lblBigTotal.Tag) : 0;
            int people = (int)numSplitPeople.Value;
            if (people < 1) people = 1;
            long perPerson = (total + people - 1) / people;
            lblSplitResult.Text = Theme.Cop(perPerson) + " c/u";

            string rawCash = txtCashReceived.Text.Trim().Replace(".", "").Replace(",", "");
            long cash = 0;
            long.TryParse(rawCash, out cash);

            if (cash <= 0 || total <= 0)
            {
                lblCashChange.ForeColor = Theme.TextMuted;
                lblCashChange.Text = "Cambio: $0";
            }
            else if (cash >= total)
            {
                lblCashChange.ForeColor = Theme.StatusGreen;
                lblCashChange.Text = "Cambio: " + Theme.Cop(cash - total);
            }
            else
            {
                lblCashChange.ForeColor = Theme.StatusRed;
                lblCashChange.Text = "Faltan: " + Theme.Cop(total - cash);
            }
        }

        private void RenderInventoryList()
        {
            string q = txtInvSearch != null ? txtInvSearch.Text.Trim().ToLowerInvariant() : "";
            string cat = cbInvCategoryFilter != null && cbInvCategoryFilter.SelectedItem != null
                ? Convert.ToString(cbInvCategoryFilter.SelectedItem)
                : "Todas";

            int prevPid = lvProducts.SelectedItems.Count > 0 ? Convert.ToInt32(lvProducts.SelectedItems[0].Tag) : 0;

            lvProducts.BeginUpdate();
            lvProducts.Items.Clear();

            foreach (Dictionary<string, object> p in currentProducts)
            {
                string name = Convert.ToString(p["name"]);
                string pCat = Convert.ToString(p["category"]);
                if (cat != "Todas" && pCat != cat) continue;
                if (!string.IsNullOrEmpty(q) && !name.ToLowerInvariant().Contains(q)) continue;

                int pid = Convert.ToInt32(p["id"]);
                bool isLow = Convert.ToBoolean(p["low_stock"]);
                ListViewItem item = new ListViewItem(new string[] {
                    pid.ToString(),
                    name,
                    pCat,
                    Theme.Cop(p["price_cop"]),
                    Convert.ToString(p["stock"]) + " unid.",
                    Convert.ToString(p["min_stock"]) + " unid.",
                    isLow ? "¡STOCK BAJO!" : "Disponible"
                });
                item.Tag = pid;
                item.ForeColor = isLow ? Theme.StatusRed : Theme.TextBone;
                if (pid == prevPid) item.Selected = true;
                lvProducts.Items.Add(item);
            }

            lvProducts.EndUpdate();
        }

        private void RenderAdminTables(Dictionary<string, object> admin)
        {
            if (!session.IsAdmin || lvUsers == null) return;

            int prevUid = lvUsers.SelectedItems.Count > 0 ? Convert.ToInt32(lvUsers.SelectedItems[0].Tag) : 0;

            ArrayList users = admin.ContainsKey("users") ? admin["users"] as ArrayList : null;
            lvUsers.BeginUpdate();
            lvUsers.Items.Clear();
            if (users != null)
            {
                foreach (Dictionary<string, object> u in users)
                {
                    int uid = Convert.ToInt32(u["id"]);
                    string r = Convert.ToString(u.ContainsKey("role") ? u["role"] : "vendedor");
                    ListViewItem item = new ListViewItem(new string[] {
                        uid.ToString(),
                        Convert.ToString(u["full_name"]),
                        Convert.ToString(u["email"]),
                        r.ToUpperInvariant(),
                        Convert.ToString(u["created_at"])
                    });
                    item.Tag = uid;
                    item.SubItems[0].Tag = r;
                    item.ForeColor = r == "administrador" ? Theme.AccentAmberLight : Theme.TextBone;
                    if (uid == prevUid) item.Selected = true;
                    lvUsers.Items.Add(item);
                }
            }
            lvUsers.EndUpdate();

            ArrayList sessionsList = admin.ContainsKey("sessions") ? admin["sessions"] as ArrayList : null;
            lvSessions.BeginUpdate();
            lvSessions.Items.Clear();
            if (sessionsList != null)
            {
                foreach (Dictionary<string, object> s in sessionsList)
                {
                    bool act = Convert.ToBoolean(s["active"]);
                    string sr = Convert.ToString(s.ContainsKey("role") ? s["role"] : "vendedor").ToUpperInvariant();
                    ListViewItem item = new ListViewItem(new string[] {
                        Convert.ToString(s["full_name"]),
                        Convert.ToString(s["email"]),
                        sr,
                        Convert.ToString(s["created_at"]),
                        act ? "ACTIVA" : "EXPIRADA"
                    });
                    item.ForeColor = act ? Theme.StatusGreen : Theme.TextMuted;
                    lvSessions.Items.Add(item);
                }
            }
            lvSessions.EndUpdate();

            ArrayList sales = admin.ContainsKey("recent_sales") ? admin["recent_sales"] as ArrayList : null;
            lvSales.BeginUpdate();
            lvSales.Items.Clear();
            if (sales != null)
            {
                foreach (Dictionary<string, object> s in sales)
                {
                    lvSales.Items.Add(new ListViewItem(new string[] {
                        "#" + Convert.ToString(s["id"]),
                        Convert.ToString(s["table_label"]),
                        Convert.ToString(s["items_summary"]),
                        Convert.ToString(s["payment_method"]),
                        Theme.Cop(s["total_cop"]),
                        Convert.ToString(s["created_at"])
                    }));
                }
            }
            lvSales.EndUpdate();
        }

        /* ================= ACCIONES ASÍNCRONAS ================= */
        private void ExecuteActionAsync(string method, string path, object payload, Action<Dictionary<string, object>> onSuccess)
        {
            lblConnState.ForeColor = Theme.AccentAmberLight;
            lblConnState.Text = "● Guardando...";

            ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    Dictionary<string, object> res = ApiClient.Request(session.ServerUrl, session.Token, method, path, payload);
                    if (!IsDisposed && IsHandleCreated)
                    {
                        BeginInvoke((MethodInvoker)delegate
                        {
                            if (onSuccess != null) onSuccess(res);
                            RefreshDashboardAsync(false);
                        });
                    }
                }
                catch (Exception ex)
                {
                    if (!IsDisposed && IsHandleCreated)
                    {
                        BeginInvoke((MethodInvoker)delegate
                        {
                            lblConnState.ForeColor = Theme.StatusRed;
                            lblConnState.Text = "● Atención";
                            MessageBox.Show(ex.Message, "Barrica POS", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                        });
                    }
                }
            });
        }

        private void AddOrderToTableAsync()
        {
            if (selectedTableId <= 0)
            {
                MessageBox.Show("Selecciona primero una mesa del salón.", "Barrica POS", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            ProductComboItem prod = cbOrderProduct.SelectedItem as ProductComboItem;
            if (prod == null)
            {
                MessageBox.Show("No hay productos disponibles en esta categoría.", "Barrica POS", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            int qty = (int)numOrderQty.Value;
            Dictionary<string, object> payload = new Dictionary<string, object>();
            payload["product_id"] = prod.Id;
            payload["quantity"] = qty;

            ExecuteActionAsync("POST", "/api/bar/tables/" + selectedTableId + "/orders", payload, delegate
            {
                numOrderQty.Value = 1;
            });
        }

        private void RemoveSelectedOrderAsync()
        {
            if (lvOrders.SelectedItems.Count == 0)
            {
                MessageBox.Show("Selecciona en la lista de la derecha el producto que deseas quitar.", "Barrica POS", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            int oid = Convert.ToInt32(lvOrders.SelectedItems[0].Tag);
            ExecuteActionAsync("DELETE", "/api/bar/orders/" + oid, null, null);
        }

        private void MarkTableForBillAsync()
        {
            if (selectedTableId <= 0) return;
            Dictionary<string, object> payload = new Dictionary<string, object>();
            payload["status"] = "por_cobrar";
            ExecuteActionAsync("POST", "/api/bar/tables/" + selectedTableId + "/status", payload, null);
        }

        private void CheckoutTableAsync()
        {
            if (selectedTableId <= 0) return;
            string method = Convert.ToString(cbPayMethod.SelectedItem ?? "Efectivo");
            Dictionary<string, object> payload = new Dictionary<string, object>();
            payload["payment_method"] = method;

            ExecuteActionAsync("POST", "/api/bar/tables/" + selectedTableId + "/checkout", payload, delegate(Dictionary<string, object> res)
            {
                txtCashReceived.Text = "";
                string totalFormatted = res.ContainsKey("total_cop") ? Theme.Cop(res["total_cop"]) : lblBigTotal.Text;
                MessageBox.Show(
                    "Cobro registrado en MySQL por " + totalFormatted + " (" + method + ").\nLa mesa quedó libre inmediatamente.",
                    "Cuenta cobrada",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information
                );
            });
        }

        private void CreateTableAsync()
        {
            int num;
            if (!int.TryParse(txtNewTableNum.Text.Trim(), out num) || num <= 0)
            {
                MessageBox.Show("Escribe un número de mesa válido.", "Nueva mesa", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            Dictionary<string, object> payload = new Dictionary<string, object>();
            payload["table_number"] = num;
            payload["label"] = txtNewTableName.Text.Trim();
            payload["capacity"] = (int)numNewTableCap.Value;

            ExecuteActionAsync("POST", "/api/bar/tables", payload, delegate
            {
                txtNewTableNum.Text = (num + 1).ToString();
                txtNewTableName.Text = "Mesa " + (num + 1) + " · Salón";
            });
        }

        private void DeleteSelectedTableAsync()
        {
            if (selectedTableId <= 0) return;
            if (MessageBox.Show("¿Eliminar esta mesa libre del salón?", "Confirmar", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
                return;

            int idToDelete = selectedTableId;
            ExecuteActionAsync("DELETE", "/api/bar/tables/" + idToDelete, null, delegate
            {
                selectedTableId = 0;
            });
        }

        private void AdjustSelectedStockAsync(int delta)
        {
            if (lvProducts.SelectedItems.Count == 0)
            {
                MessageBox.Show("Haz clic primero sobre un producto en la tabla de inventario.", "Inventario", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            int pid = Convert.ToInt32(lvProducts.SelectedItems[0].Tag);
            Dictionary<string, object> payload = new Dictionary<string, object>();
            payload["delta"] = delta;
            ExecuteActionAsync("POST", "/api/bar/products/" + pid + "/stock", payload, null);
        }

        private void DeleteSelectedProductAsync()
        {
            if (lvProducts.SelectedItems.Count == 0)
            {
                MessageBox.Show("Selecciona primero un producto para eliminarlo.", "Inventario", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            int pid = Convert.ToInt32(lvProducts.SelectedItems[0].Tag);
            if (MessageBox.Show("¿Eliminar este producto del inventario en MySQL?", "Confirmar eliminación", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
                return;

            ExecuteActionAsync("DELETE", "/api/bar/products/" + pid, null, null);
        }

        private void CreateProductAsync()
        {
            int price, stock, min;
            if (!int.TryParse(txtProdPrice.Text.Trim(), out price) || price <= 0 ||
                !int.TryParse(txtProdStock.Text.Trim(), out stock) || stock < 0 ||
                !int.TryParse(txtProdMin.Text.Trim(), out min) || min < 0)
            {
                MessageBox.Show("Verifica que el precio sea mayor a 0 y que el stock sea numérico.", "Inventario", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            Dictionary<string, object> payload = new Dictionary<string, object>();
            payload["name"] = txtProdName.Text.Trim();
            payload["category"] = Convert.ToString(cbProdCategory.SelectedItem ?? "Licores");
            payload["price_cop"] = price;
            payload["stock"] = stock;
            payload["min_stock"] = min;

            ExecuteActionAsync("POST", "/api/bar/products", payload, delegate
            {
                txtProdName.Text = "";
            });
        }

        private void ToggleSelectedUserRoleAsync()
        {
            if (lvUsers == null || lvUsers.SelectedItems.Count == 0)
            {
                MessageBox.Show("Selecciona un usuario en la tabla «Equipo y Roles» para cambiar su perfil.", "Administración", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            int uid = Convert.ToInt32(lvUsers.SelectedItems[0].Tag);
            string currentRole = Convert.ToString(lvUsers.SelectedItems[0].SubItems[0].Tag ?? "vendedor");
            string nextRole = currentRole == "administrador" ? "vendedor" : "administrador";

            Dictionary<string, object> payload = new Dictionary<string, object>();
            payload["role"] = nextRole;
            ExecuteActionAsync("POST", "/api/bar/users/" + uid + "/role", payload, null);
        }

        private void PerformLogout()
        {
            ThreadPool.QueueUserWorkItem(delegate
            {
                try { ApiClient.Request(session.ServerUrl, session.Token, "POST", "/api/auth/logout", new Dictionary<string, object>()); }
                catch { }
            });
            LogoutRequested = true;
            Close();
        }

        private sealed class ProductComboItem
        {
            public int Id;
            public string Display;
            public override string ToString() { return Display; }
        }
    }

    internal static class Program
    {
        [DllImport("user32.dll")]
        private static extern bool SetProcessDPIAware();

        [STAThread]
        public static void Main()
        {
            try { SetProcessDPIAware(); } catch { }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            string serverUrl = "http://127.0.0.1:5000";
            while (true)
            {
                SessionContext activeSession = null;
                using (LoginForm login = new LoginForm(serverUrl))
                {
                    if (login.ShowDialog() == DialogResult.OK && login.AuthenticatedSession != null)
                    {
                        activeSession = login.AuthenticatedSession;
                        serverUrl = activeSession.ServerUrl;
                    }
                    else
                    {
                        break;
                    }
                }

                bool reopenLogin = false;
                using (MainForm main = new MainForm(activeSession))
                {
                    Application.Run(main);
                    reopenLogin = main.LogoutRequested;
                }
                if (!reopenLogin) break;
            }
        }
    }
}
