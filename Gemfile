source "https://rubygems.org"

git_source(:github) do |repo_name|
  repo_name = "#{repo_name}/#{repo_name}" unless repo_name.include?("/")
  "https://github.com/#{repo_name}.git"
end

ruby "2.5.1"

gem "autoprefixer-rails"
gem "flutie"
gem "honeybadger"
gem "jquery-rails"
gem "pg", "~> 0.18"
gem "puma"
gem "rack-canonical-host"
gem "rails", "~> 5.2.0"
gem "recipient_interceptor"
gem "sass-rails", "~> 5.0"
gem "skylight"
gem "sprockets", ">= 3.0.0"
gem "title"
gem "uglifier"
gem "bootsnap", require: false


group :development do
  gem "listen"
  gem "rack-mini-profiler", require: false
  gem "spring"
  gem "web-console"
end

group :development, :test do
  gem "awesome_print"
  gem "bundler-audit", ">= 0.5.0", require: false
  gem "dotenv-rails"
  gem "factory_bot_rails"
  gem "pry-byebug"
  gem "pry-rails"
end

group :test do
  gem "formulaic"
  gem "launchy"
  gem "simplecov", require: false
  gem "timecop"
  gem "webmock"
  gem "rspec-rails"
end

gem "suspenders", group: [:development, :test], github: "thoughtbot/suspenders"