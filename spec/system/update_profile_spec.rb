require "rails_helper"

describe "updating your profile" do
  it "can update your first and last name" do
    user = create(:user)
    login_as(user)

    click_link "My Profile"

    fill_in "Full name", with: "Ian Anderson"
    click_on "Update Profile"

    expect(page).to have_content "Profile updated"

    click_on "Add Trophy"
    expect(page).to have_content "Add a trophy for Ian Anderson"
  end
end
