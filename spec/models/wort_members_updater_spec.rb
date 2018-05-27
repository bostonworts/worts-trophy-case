require "rails_helper"

describe WortMembersUpdater, ".update" do
  it "create new User records if they don't exist" do
    WortMembersUpdater.update(subscribed_emails: %w(foo@example.com))

    expect(User.exists?(admin: false, email: "foo@example.com")).to eq true
  end

  it "doesn't deactivate existing User records if they're still in the list" do
    existing_user = create(:user)

    WortMembersUpdater.update(subscribed_emails: [existing_user.email])

    existing_user.reload
    expect(existing_user.reload).not_to be_deactivated
  end

  it "deactivates existing User records if they're no longer in the list" do
    existing_user = create(:user)

    WortMembersUpdater.update(subscribed_emails: [])

    existing_user.reload
    expect(existing_user.reload).to be_deactivated
  end
end
