using System.Diagnostics;
using System.IO.Compression;
using System.Net;
using System.Text;
using System.Windows.Forms;

namespace ChatGPTGraphifyInstaller;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new InstallerForm());
    }
}

internal sealed class InstallerForm : Form
{
    private const string PythonInstallerUrl = "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe";
    private const string SourceZipUrl = "https://github.com/andrewPillai/chatgpt-graphify/archive/refs/heads/updates.zip";

    private readonly TextBox log = new() { Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical };
    private readonly Button installButton = new() { Text = "Install ChatGPT Graphify", AutoSize = true };
    private readonly ProgressBar progress = new() { Style = ProgressBarStyle.Marquee, Visible = false };
    private readonly Label status = new() { AutoSize = true, Text = "Ready to install." };

    private string InstallRoot => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "ChatGPT Graphify");
    private string VenvRoot => Path.Combine(InstallRoot, "venv");
    private string SourceRoot => Path.Combine(InstallRoot, "source");

    public InstallerForm()
    {
        Text = "ChatGPT Graphify Installer";
        Width = 700;
        Height = 480;
        StartPosition = FormStartPosition.CenterScreen;
        MinimizeBox = false;
        MaximizeBox = false;

        var title = new Label
        {
            Text = "ChatGPT Graphify",
            Font = new Font(Font.FontFamily, 18, FontStyle.Bold),
            AutoSize = true,
            Location = new Point(20, 18),
        };
        var description = new Label
        {
            Text = "This installer checks for Python, installs it if needed, and creates a desktop launcher.",
            AutoSize = true,
            Location = new Point(22, 55),
        };
        status.Location = new Point(22, 88);
        progress.Location = new Point(22, 115);
        progress.Width = 640;
        installButton.Location = new Point(22, 145);
        installButton.Click += (_, _) => Install();
        log.Location = new Point(22, 195);
        log.Width = 640;
        log.Height = 220;

        Controls.AddRange([title, description, status, progress, installButton, log]);
    }

    private async void Install()
    {
        installButton.Enabled = false;
        progress.Visible = true;
        try
        {
            Directory.CreateDirectory(InstallRoot);
            var python = FindPython();
            if (python is null)
            {
                await InstallPython();
                python = FindPython();
            }

            if (python is null)
                throw new InvalidOperationException("Python could not be found after installation.");

            Log("Python is ready.");
            var source = await DownloadSource();
            await Run(python, $"-m venv \"{VenvRoot}\"");
            var venvPython = Path.Combine(VenvRoot, "Scripts", "python.exe");
            await Run(venvPython, "-m pip install --upgrade pip");
            await Run(venvPython, $"-m pip install \"{source}\"");

            var pythonw = Path.Combine(VenvRoot, "Scripts", "pythonw.exe");
            CreateShortcut(pythonw);
            Log("A ChatGPT Graphify shortcut was added to your desktop.");
            status.Text = "Installation complete.";
            MessageBox.Show("ChatGPT Graphify is installed. Use the desktop shortcut to choose a folder and start.", "Installation complete", MessageBoxButtons.OK, MessageBoxIcon.Information);
            Process.Start(new ProcessStartInfo(pythonw, "-m chatgpt_graphify.desktop") { UseShellExecute = true });
        }
        catch (Exception ex)
        {
            status.Text = "Installation failed.";
            Log("ERROR: " + ex.Message);
            MessageBox.Show(ex.Message, "Installation failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally
        {
            progress.Visible = false;
            installButton.Enabled = true;
        }
    }

    private string? FindPython()
    {
        foreach (var candidate in new[] { "py", "python" })
        {
            try
            {
                var result = RunSync(candidate, candidate == "py" ? "-3 --version" : "--version");
                if (result.ExitCode == 0 && result.Output.Contains("Python 3."))
                    return candidate;
            }
            catch { }
        }
        return null;
    }

    private async Task InstallPython()
    {
        status.Text = "Python was not found. Downloading Python…";
        Log("Downloading Python from python.org…");
        var installer = Path.Combine(Path.GetTempPath(), "chatgpt-graphify-python.exe");
        using var client = new WebClient();
        await client.DownloadFileTaskAsync(new Uri(PythonInstallerUrl), installer);
        status.Text = "Installing Python for your user account…";
        Log("Installing Python without administrator access…");
        var result = await Run(installer, "/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_test=0 SimpleInstall=1");
        File.Delete(installer);
        if (result != 0)
            throw new InvalidOperationException("The Python installer returned exit code " + result + ".");
    }

    private async Task<string> DownloadSource()
    {
        status.Text = "Downloading Graphify…";
        Log("Downloading the latest Graphify source…");
        var zip = Path.Combine(Path.GetTempPath(), "chatgpt-graphify-source.zip");
        using var client = new WebClient();
        await client.DownloadFileTaskAsync(new Uri(SourceZipUrl), zip);
        if (Directory.Exists(SourceRoot)) Directory.Delete(SourceRoot, true);
        var extract = Path.Combine(Path.GetTempPath(), "chatgpt-graphify-source");
        if (Directory.Exists(extract)) Directory.Delete(extract, true);
        ZipFile.ExtractToDirectory(zip, extract);
        File.Delete(zip);
        var extractedRoot = Directory.GetDirectories(extract).Single();
        Directory.Move(extractedRoot, SourceRoot);
        Directory.Delete(extract, true);
        return SourceRoot;
    }

    private async Task<int> Run(string fileName, string arguments)
    {
        var start = new ProcessStartInfo(fileName, arguments)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        using var process = Process.Start(start) ?? throw new InvalidOperationException($"Could not start {fileName}.");
        var output = await process.StandardOutput.ReadToEndAsync();
        var error = await process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync();
        if (!string.IsNullOrWhiteSpace(output)) Log(output.Trim());
        if (process.ExitCode != 0)
            throw new InvalidOperationException($"{fileName} failed with exit code {process.ExitCode}: {error.Trim()}");
        return process.ExitCode;
    }

    private static (int ExitCode, string Output) RunSync(string fileName, string arguments)
    {
        using var process = Process.Start(new ProcessStartInfo(fileName, arguments)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        }) ?? throw new InvalidOperationException();
        var output = process.StandardOutput.ReadToEnd() + process.StandardError.ReadToEnd();
        process.WaitForExit();
        return (process.ExitCode, output);
    }

    private void CreateShortcut(string pythonw)
    {
        var desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        var shortcut = Path.Combine(desktop, "ChatGPT Graphify.lnk");
        var script = $"$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut('{Escape(desktop)}\\ChatGPT Graphify.lnk'); $s.TargetPath='{Escape(pythonw)}'; $s.Arguments='-m chatgpt_graphify.desktop'; $s.WorkingDirectory='{Escape(InstallRoot)}'; $s.Save()";
        var encoded = Convert.ToBase64String(Encoding.Unicode.GetBytes(script));
        var result = RunSync("powershell", $"-NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded}");
        if (result.ExitCode != 0 || !File.Exists(shortcut))
            throw new InvalidOperationException("The desktop shortcut could not be created.");
    }

    private static string Escape(string value) => value.Replace("'", "''");

    private void Log(string message)
    {
        if (InvokeRequired)
        {
            BeginInvoke(() => Log(message));
            return;
        }
        log.AppendText(message + Environment.NewLine);
        log.SelectionStart = log.TextLength;
        log.ScrollToCaret();
    }
}
