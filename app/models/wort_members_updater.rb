class WortMembersUpdater
  def self.update(subscribed_emails:)
    User.transaction do
      created_count = 0

      subscribed_emails.each do |subscribed_email|
        User.find_or_create_by!(email: subscribed_email) do |user|
          user.admin = false
          user.full_name = "Worts Member"
          created_count += 1
        end
      end

      no_longer_subscribed_members = User.where.not(email: subscribed_emails)
      deactivated_count = no_longer_subscribed_members.update_all(deactivated_at: Time.now)

      {
        created_count: created_count,
        deactivated_count: deactivated_count,
      }
    end
  end
end
