module System
  def login_as(user)
    visit "/"

    click_link "Add Trophy"

    # Submit login form with email address in worts list
    expect(current_path).to eq("/users/sign_in")

    fill_in "Worts email", with: user.email
    click_on "Send magic link"

    # Open email, visit link in email to log in
    emails = ActionMailer::Base.deliveries
    expect(emails.size).to eq(1)

    magic_link_url = emails.first.body.raw_source.match(/http:\/\/[\S]+/)

    visit magic_link_url

    # It redirects to root in test because the session is cleared out
    # In development, it redirects you back to where you wanted to go initially
    click_link "Add Trophy"

    # Now we're logged in so it doesn't redirect
    expect(current_path).to eq("/trophies/new")
  end
end
