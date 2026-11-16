using System;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media.Imaging;

namespace GoldTicker.Wpf;

public partial class InfoWindow : Window
{
    public InfoWindow(string title, string body, string okText, bool alignLeft = false)
    {
        InitializeComponent();
        Title = title;
        TitleBlock.Text = title;
        BodyBlock.Text = body;
        BodyBlock.TextAlignment = alignLeft ? TextAlignment.Left : TextAlignment.Center;
        OkText.Text = okText;
        try
        {
            AppIcon.Source = new BitmapImage(new Uri("pack://application:,,,/Assets/icon.png", UriKind.Absolute));
        }
        catch
        {
            AppIcon.Visibility = Visibility.Collapsed;
        }
    }

    private void Border_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        if (e.ButtonState == MouseButtonState.Pressed)
            DragMove();
    }

    private void OkButton_Click(object sender, RoutedEventArgs e) => Close();
}
